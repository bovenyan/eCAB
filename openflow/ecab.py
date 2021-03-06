# Copyright (C) 2014 High Speed Network Labtory, Polytechnic School of
# Engineering, NYU
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import threading
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls, HANDSHAKE_DISPATCHER
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto import ether
from ryu.ofproto import inet
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import icmp
from ryu.lib.packet import ipv4
# from ryu.lib import mac
from ryu import utils
# import random
from cab_client import *
import pickle
import copy


class CABSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(CABSwitch, self).__init__(*args, **kwargs)
        self.cab = cab_client()
        # self.cab.create_connection()
        self.overflow_cnt = 0
        self.is_overflow = False
        self.queries = 0
        self.packetin = 0
        self.packetout = 0
        self.flowmod = 0
        # self.tracefile = raw_input('Enter Tracename: ')
        self.buckets = {}
        self.query_map = {}
        self.portMap = pickle.load(open("portMap.dat", 'rb'))
        self.pathMap = pickle.load(open("pathMap.dat", 'rb'))
        self.datapathList = {}

        c = threading.Thread(target=self.clean_query_map)
        c.start()

    def id_to_ipInt(self, ID):
        return 167772160 + ID

    def ipInt_to_id(self, ipInt):
        return ipInt - 167772160

    def add_flow(self, datapath, table_id, priority, match, inst, buffer_id,
                 hard_timeout=60):
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(datapath=datapath, hard_timeout=hard_timeout,
                                table_id=table_id, priority=priority,
                                match=match, instructions=inst,
                                buffer_id=buffer_id)
        datapath.send_msg(mod)
        # self.flowmod += 1

    def gen_defaults(self, datapath, Type=None, toCntr=True):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()

        if Type == "arp":
            match.set_dl_type(ether.ETH_TYPE_ARP)
        if Type == "ip":
            match.set_dl_type(ether.ETH_TYPE_IP)
        if Type == "icmp":
            match.set_dl_type(ether.ETH_TYPE_IP)
            match.set_ip_proto(inet.IPPROTO_ICMP)
        # TCP ...

        actions = []
        if toCntr:
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        self.add_flow(datapath, 0, 0, match, inst, ofproto.OFP_NO_BUFFER, 0)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        # install table-miss flow entry
        self.logger.info('OFPSwitchFeatures datapath_id=0x%016x n_buffers=%d \
                         n_tables=%d auxiliary_id=%d capabilities=0x%08x' %
                         (msg.datapath_id, msg.n_buffers, msg.n_tables,
                          msg.auxiliary_id, msg.capabilities))
        # First, clear table entries
        mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE)
        datapath.send_msg(mod)
        # set table0 default rule: go to controller

        self.gen_defaults(datapath, "arp")
        self.gen_defaults(datapath, "icmp")

        self.datapathList[datapath.id] = datapath
        # set table1 default : drop
        # inst2 = []
        # self.add_flow(datapath, 1, 0, match, inst2, ofproto.OFP_NO_BUFFER, 0)

        # m = threading.Thread(target=self.monitor)
        # m.start()

    @set_ev_cls(ofp_event.EventOFPErrorMsg, [HANDSHAKE_DISPATCHER,
                                             CONFIG_DISPATCHER,
                                             MAIN_DISPATCHER])
    def error_msg_handler(self, ev):
        msg = ev.msg
        self.logger.info('OFPErrorMsg received: type=0x%02x code=0x%02x \
                         message=%s', msg.type,
                         msg.code, utils.hex_array(msg.data))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        self.packetin += 1
        msg = ev.msg
        in_port = msg.match['in_port']

        datapath = msg.datapath
        # dpid = datapath.id

        ofproto = datapath.ofproto

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            # data = msg.data
            self.overflow_cnt += 1
            if self.is_overflow is False:
                self.is_overflow = True
        else:
            self.is_overflow = False

        pkt = packet.Packet(msg.data)

        # parse ethernet header
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        ethertype = eth_pkt.ethertype

        if ethertype == ether.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            self.handle_arp(datapath, eth_pkt, arp_pkt, in_port)
            return

        if ethertype == ether.ETH_TYPE_IP:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            actions = self.handle_ip(datapath, pkt, ip_pkt, in_port)
            # print actions
            self.send_packet_out(datapath, msg, in_port, actions)

    def send_packet_out(self, datapath, msg, in_port, actions=[]):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        data = None

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def handle_arp(self, datapath, eth_pkt, arp_pkt, in_port):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # print arp_pkt.dst_ip
        temp = arp_pkt.dst_ip.split('.')
        idstr = hex(int(temp[3]))[2:]
        arp_resolv_mac = ""

        if len(idstr) == 1:
            arp_resolv_mac = "00:00:00:00:00:0" + idstr
        elif len(idstr) == 2:
            arp_resolv_mac = "00:00:00:00:00:" + idstr
        else:
            print "Too many hosts"
            return

        # print "resolved: " + arp_resolv_mac
        ether_hd = ethernet.ethernet(dst=eth_pkt.src,
                                     src=arp_resolv_mac,
                                     ethertype=ether.ETH_TYPE_ARP)
        arp_hd = arp.arp(hwtype=1, opcode=arp.ARP_REPLY,
                         src_mac=arp_resolv_mac, src_ip=arp_pkt.dst_ip,
                         dst_mac=eth_pkt.src, dst_ip=arp_pkt.src_ip)
        arp_reply = packet.Packet()
        arp_reply.add_protocol(ether_hd)
        arp_reply.add_protocol(arp_hd)
        arp_reply.serialize()
        data = arp_reply.data
        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(datapath, ofproto.OFP_NO_BUFFER,
                                  ofproto.OFPP_CONTROLLER, actions, data)
        datapath.send_msg(out)

    def handle_ping(self, datapath, ip_pkt, in_port):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # extract destination
        srcHost = ip_pkt.src
        src_dpid = int(srcHost.split('.')[3])
        dstHost = ip_pkt.dst
        dst_dpid = int(dstHost.split('.')[3])

        # if not the fisrt packet of the flow, don't query eCAB
        # key = srcHost + dstHost

        # if key in self.query_map:
        # drop the packet
        #    return
        # self.query_map[key] = time.time()

        # TODO: query eCAB
        # request = pkt_h(ipv4_to_int(ip_src), ipv4_to_int(ip_dst),
        #                src_port, dst_port)
        # rules = self.cab.query(request)

        # extract path and port
        path = self.pathMap[src_dpid][dst_dpid]
        # print path
        dpidPorts = []  # [dpid, srcPort, dstPort]
        sPort = 1  # sPort = 1

        for idx in range(len(path)-1):
            curDPID = path[idx]
            dPort = self.portMap[curDPID][1][path[idx+1]]
            dpidPorts.append([curDPID, sPort, dPort])
            sPort = self.portMap[path[idx+1]][1][curDPID]

        dpidPorts.append([dst_dpid, sPort, 1])

        # print dpidPorts

        thisAction = []
        for rec in reversed(dpidPorts):
            # TODO Insert ten redundant flows
            """
            for redIdx in range(10):
                matchRed = parser.OFPMatch()
                matchRed.set_dl_type(ether.ETH_TYPE_IP)
                matchRed.set_ipv4_dst(self.id_to_ipInt(redIdx)*2)
                matchRed.set_ip_proto(inet.IPPROTO_TCP)
                actions = [parser.OFPActionOutput(1)]
                inst = [parser.OFPInstructionActions(
                    ofproto.OFPIT_APPLY_ACTIONS,
                    actions)]
                self.add_flow(self.datapathList[rec[0]],
                              0, 100, matchRed, inst,
                              ofproto.OFP_NO_BUFFER, 3)
            """
            # forward
            matchFwd = parser.OFPMatch()
            matchFwd.set_in_port(rec[1])
            matchFwd.set_dl_type(ether.ETH_TYPE_IP)
            matchFwd.set_ipv4_src(self.id_to_ipInt(src_dpid))
            matchFwd.set_ipv4_dst(self.id_to_ipInt(dst_dpid))
            matchFwd.set_ip_proto(inet.IPPROTO_ICMP)
            actions = [parser.OFPActionOutput(rec[2])]

            if (datapath.id == rec[0]):
                # print "dpid: s" + str(rec[0]) + " output: " + str(rec[2])
                thisAction = copy.deepcopy(actions)

            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                                 actions)]
            self.add_flow(self.datapathList[rec[0]],
                          0, 100, matchFwd, inst,
                          ofproto.OFP_NO_BUFFER, 5)

            # backward
            matchBwd = parser.OFPMatch()
            matchBwd.set_in_port(rec[2])
            matchBwd.set_dl_type(ether.ETH_TYPE_IP)
            matchBwd.set_ipv4_src(self.id_to_ipInt(dst_dpid))
            matchBwd.set_ipv4_dst(self.id_to_ipInt(src_dpid))
            matchBwd.set_ip_proto(inet.IPPROTO_ICMP)
            actions = [parser.OFPActionOutput(rec[1])]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                                 actions)]
            self.add_flow(self.datapathList[rec[0]],
                          0, 100, matchBwd, inst,
                          ofproto.OFP_NO_BUFFER, 5)

        # print thisAction
        return thisAction
        # cache

        # actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD, 0)]
        # inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
        #                                      actions)]
        # self.add_flow(datapath, 0, 200, match, inst, msg.buffer_id, 1)
        # if msg.buffer_id == ofproto.OFP_NO_BUFFER:
        #     self.handle_no_buffer(datapath, msg.data, in_port)

    def handle_ip(self, datapath, pkt, ip_pkt, in_port):
        actions = []
        if ip_pkt.proto == inet.IPPROTO_ICMP:
            icmp_pkt = pkt.get_protocol(icmp.icmp)
            icmp_type = icmp_pkt.type

            if icmp_type == 8 or icmp_type == 0:
                actions = self.handle_ping(datapath, ip_pkt, in_port)

        return actions  # boven: do nothing if it's not icmp
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # try to parse ip header
        ip_header = pkt.get_protocol(ipv4.ipv4)
        self.logger.debug('ip src %s dst %s', ip_header.src, ip_header.dst)
        ip_src = ip_header.src
        ip_dst = ip_header.dst

        # try to parse icmp
        if ip_header.proto == inet.IPPROTO_ICMP:
            self.handle_ping(datapath, msg, in_port)
            return

        if ip_header.proto != inet.IPPROTO_TCP:
            self.send_packet_out(datapath, msg, in_port)
            return
        # try to parse eth header and convert addrs to tcp ports
        eth = pkt.get_protocol(ethernet.ethernet)
        src_port = eth_to_int(eth.src)
        dst_port = eth_to_int(eth.dst)

        key = ip_src+ip_dst+str(src_port)+str(dst_port)
        # if not the fisrt packet of the flow, don't query CAB
        if key in self.query_map:
            self.send_packet_out(datapath, msg, in_port)
            return
        self.query_map[key] = time.time()

        request = pkt_h(ipv4_to_int(ip_src), ipv4_to_int(ip_dst),
                        src_port, dst_port)

        # request_str = str(ip_src)+'\t'+str(ip_dst)+ \
        #    '\t'+str(eth.src)+'\t'+str(eth.dst)+'\n'
        # with open('queries', 'a') as q:
        #         string = str(time.time()) + '\t' + request_str + '\n'
        #         q.write(string)
        # print string

        self.queries += 1
        rules = self.cab.query(request)
        if rules is None:
            self.logger.error("error\trequest rules for packet failed: \
                              %s %s %s %s", ip_src, ip_dst, eth.src, eth.dst)
            return

        timeout = random.randint(20, 30)

        # If there is more than one query hit the same bucket
        # before the bucket been installed,
        # only need to flowmod the bucket once.
        bucket = rules[0]
        bucket_str = ipv4_to_str(bucket.ip_src) + '/' \
            + ipv4_to_str(bucket.ip_src_mask) + '\t' \
            + ipv4_to_str(bucket.ip_dst) + '/' \
            + ipv4_to_str(bucket.ip_dst_mask) + '\t' \
            + eth_to_str(bucket.port_src) + '/' \
            + eth_mask_to_str(bucket.port_src_mask) + '\t' \
            + eth_to_str(bucket.port_dst) + '/' \
            + eth_mask_to_str(bucket.port_dst_mask)
        if bucket_str not in self.buckets:
            self.buckets[bucket_str] = time.time() + timeout
            # with open('buckets', 'a') as f:
            #     string = str(time.time()) + '\t' + bucket_str + '\n'
            #     f.write(string)
        elif self.buckets[bucket_str] < time.time():
            self.buckets[bucket_str] = time.time() + timeout
        else:
            self.send_packet_out(datapath, msg, in_port)
            return

        # first install rules, rules[0] is bucket
        for rule in rules[1:]:
            match = parser.OFPMatch()
            match.set_dl_type(ether.ETH_TYPE_IP)
            # match.set_ip_proto(inet.IPPROTO_TCP)
            match.set_ipv4_src_masked(rule.ip_src, rule.ip_src_mask)
            match.set_ipv4_dst_masked(rule.ip_dst, rule.ip_dst_mask)
            # use eth_to_str to convert ports to eth addrs
            dl_src = mac.haddr_to_bin(eth_to_str(rule.port_src))
            dl_dst = mac.haddr_to_bin(eth_to_str(rule.port_dst))
            dl_src_mask = mac.haddr_to_bin(eth_mask_to_str(rule.port_src_mask))
            dl_dst_mask = mac.haddr_to_bin(eth_mask_to_str(rule.port_dst_mask))
            match.set_dl_src_masked(dl_src, dl_src_mask)
            match.set_dl_dst_masked(dl_dst, dl_dst_mask)

            actions = [parser.OFPActionOutput(3)]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                                 actions)]
            self.add_flow(datapath, 1, rule.priority, match, inst,
                          ofproto.OFP_NO_BUFFER, timeout)

            self.logger.debug("install flow %s %s %s %s %s %s %s %s",
                              ipv4_to_str(rule.ip_src),
                              ipv4_to_str(rule.ip_src_mask),
                              ipv4_to_str(rule.ip_dst),
                              ipv4_to_str(rule.ip_dst_mask),
                              eth_to_str(rule.port_src),
                              eth_mask_to_str(rule.port_src_mask),
                              eth_to_str(rule.port_dst),
                              eth_mask_to_str(rule.port_dst_mask))

        # second, send a barrier to ensure all rules installation are done
        datapath.send_barrier()

        # third, install bucket
        bucket = rules[0]
        match = parser.OFPMatch()
        match.set_dl_type(ether.ETH_TYPE_IP)
        # match.set_ip_proto(inet.IPPROTO_TCP)
        match.set_ipv4_src_masked(bucket.ip_src, bucket.ip_src_mask)
        match.set_ipv4_dst_masked(bucket.ip_dst, bucket.ip_dst_mask)
        # use eth_to_str to convert ports to eth addrs
        dl_src = mac.haddr_to_bin(eth_to_str(bucket.port_src))
        dl_dst = mac.haddr_to_bin(eth_to_str(bucket.port_dst))
        dl_src_mask = mac.haddr_to_bin(eth_mask_to_str(bucket.port_src_mask))
        dl_dst_mask = mac.haddr_to_bin(eth_mask_to_str(bucket.port_dst_mask))
        match.set_dl_src_masked(dl_src, dl_src_mask)
        match.set_dl_dst_masked(dl_dst, dl_dst_mask)

        inst = [parser.OFPInstructionGotoTable(1)]
        self.add_flow(datapath, 0, 100, match, inst, msg.buffer_id, timeout)

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            self.handle_no_buffer(datapath, msg.data, in_port)

        self.logger.debug("install bucket %s %s %s %s %s %s %s %s",
                          ipv4_to_str(bucket.ip_src),
                          ipv4_to_str(bucket.ip_src_mask),
                          ipv4_to_str(bucket.ip_dst),
                          ipv4_to_str(bucket.ip_dst_mask),
                          eth_to_str(bucket.port_src),
                          eth_mask_to_str(bucket.port_src_mask),
                          eth_to_str(bucket.port_dst),
                          eth_mask_to_str(bucket.port_dst_mask))
    """

    """
    def monitor(self):
        with open('./results/results_cab_'+self.tracefile, 'w') as f:
            f.write('time\tqueries\tPacketIn\tFlowMod\n')
            while True:
                string = str(time.time()) + '\t' + str(self.queries) + \
                    '\t' + str(self.packetin) + '\t' + str(self.flowmod) + '\n'
                f.write(string)

                time.sleep(1)
    """
    """
    def handle_no_buffer(self, datapath, data, in_port):
        ofp = datapath.ofproto
        ofp_parser = datapath.ofproto_parser
        actions = [ofp_parser.OFPActionOutput(3)]
        req = ofp_parser.OFPPacketOut(datapath, ofp.OFP_NO_BUFFER,
                                      in_port, actions, data)
        datapath.send_msg(req)
        self.packetout += 1
    """

    def clean_query_map(self):
        while True:
            time.sleep(10)
            for i in self.query_map.keys():
                if (time.time() - self.query_map[i]) > 8:
                    del self.query_map[i]
