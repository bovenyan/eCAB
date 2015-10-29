import sys

if __name__ == "__main__":
    f = open(sys.argv[1], 'rb')
    thres = float(sys.argv[2])
    lines = f.readlines()

    rtt = float(0.0)
    rttCnt = 0
    setup = float(0.0)
    setupCnt = 0

    first = True
    for line in lines:
        if line.startswith("64"):
            if first:
                first = False
                continue

            time = float(line.split(" ")[6][5:])
            if (time < thres):
                rtt = rtt + time
                rttCnt = rttCnt + 1
            else:
                setup = setup + time
                setupCnt = setupCnt + 1

    rtt = rtt/rttCnt
    setup = setup/setupCnt - rtt
    print "setup: " + str(setup) + " rtt: " + str(rtt)
