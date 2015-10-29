from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.node import RemoteController, OVSSwitch
from functools import partial
import sys
import pickle
import networkx as nx


# parsing the input file
def parseTopoFile(filename):
    nodeNo = 0

    obj = open(filename, 'r')
    lines = obj.readlines()

    G = nx.Graph()

    for line in lines:
        line = line[:-1]

        # print line
        if 'node' in line:
            temp = line.split(':')
            nodeNo = int(temp[1])

        if '-' in line:
            pairStr = line.split('-')
            G.add_edge(int(pairStr[0]), int(pairStr[1]))

    obj.close()

    return (nodeNo, G.edges(), nx.shortest_path(G))


class fabric(Topo):
    def __init__(self, topoFile, topoType=0):
        Topo.__init__(self)

        nodeNo, linkset, paths = parseTopoFile(topoFile)

        # hosts = [None] * nodeNo
        switches = [None] * nodeNo

        # select the two hosts with longest path
        longest = 0
        selPath = [None, None]

        for i in paths:
            for j in paths:
                if len(paths[i][j]) > longest:
                    longest = len(paths[i][j])
                    selPath[0] = i
                    selPath[1] = j

        print "Selected: " + str(selPath)
        print paths[selPath[0]][selPath[1]]
        # add hosts and switches
        for idx in range(nodeNo):
            switches[idx] = self.addSwitch('s'+str(idx+1))

            if (idx+1 == selPath[0] or idx+1 == selPath[1]):
                hexstr = hex(int(idx+1))[2:]
                if len(hexstr) == 1:
                    macAddr = "00:00:00:00:00:0" + hexstr
                elif len(hexstr) == 2:
                    macAddr = "00:00:00:00:00:" + hexstr
                else:
                    print "Error: Too many hosts"
                    return

                ipAddr = "10.0.0."+str(idx+1)

                host = self.addHost('h'+str(idx+1),
                                    mac = macAddr,
                                    ip = ipAddr)
                self.addLink(host, switches[idx])
                # connect a host to each

        # add links
        # print "nNode " + str(nodeNo)
        for link in linkset:
            if (link[0] <= nodeNo and link[1] <= nodeNo):
                # print "link" + str(link)
                self.addLink(switches[link[0]-1], switches[link[1]-1])
            else:
                print "invalid link: " + str(link)

        # record switch info
        # dpid, name, {next-hop: physical port}
        #
        # switchInfo format:
        #   dpid : [name, {remote dpid : port}]

        switchInfo = {}

        for idx in range(nodeNo):
            switchInfo[idx+1] = [switches[idx], {}]

        for link in linkset:
            # print "link: " + str((switches[link[0]-1], switches[link[1]-1]))
            sPort, dPort = self.port(switches[link[0]-1], switches[link[1]-1])
            # print "ports: " + str((sPort, dPort))
            switchInfo[link[0]][1][link[1]] = sPort
            switchInfo[link[1]][1][link[0]] = dPort

        pickle.dump(switchInfo, open("portMap.dat", 'wb'))
        pickle.dump(paths, open("pathMap.dat", 'wb'))

        # calculate the routings


def runTest(filename):
    # generate topology
    topo = fabric(topoFile=filename)

    net = Mininet(topo=topo, controller=RemoteController("ryu"),
                  switch=partial(OVSSwitch, protocols="OpenFlow13"))
    # net = Mininet(topo=topo, controller=OVSController)
    net.start()

    CLI(net)

    net.stop()

if __name__ == "__main__":
    runTest(sys.argv[1])
