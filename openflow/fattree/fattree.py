import sys


def genFatTree(k):
    if k % 2 != 0:
        k = k - 1

    nodeNo = 5 * k * k / 4

    filename = 'fattree-' + str(k) + '-' + str(nodeNo) + '.topo'
    fout = open(filename, 'w')

    fout.write("node: " + str(nodeNo) + '\n')
    fout.write("\n")
    fout.write("link:\n")

    # edge switch
    for edgeIdx in range(k*k/2):
        offset = edgeIdx/(k/2)*(k/2) + k*k/2

        for podOffset in range(k/2):
            fout.write(str(edgeIdx + 1) + '-' +
                       str(offset + podOffset + 1) + '\n')
    # agg switch
    for aggIdx in range(k*k/2):
        podIdx = aggIdx / (k/2)
        InPodIdx = aggIdx % (k/2)

        for coreOffset in range(k/2):
            coreID = ((podIdx + InPodIdx * k/2) + coreOffset) % (k*k/4)
            fout.write(str(aggIdx + k*k/2 + 1) + '-' +
                       str(coreID + k*k + 1) + '\n')

if __name__ == "__main__":
    genFatTree(int(sys.argv[1]))
