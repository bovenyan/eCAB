import sys


def transFile(filename):
    if filename.find(".alt") == -1:
        return

    fin = open(filename, 'r')
    filename = filename.replace(".alt", ".topo")
    fout = open(filename, 'w')

    lines = fin.readlines()

    temps = lines[1].split(" ")
    nodeNo = int(temps[0])

    fout.write("node: " + str(nodeNo) + '\n')
    fout.write("\n")
    fout.write("link:\n")

    curIdx = 3

    while lines[curIdx].find("EDGES") == -1:
        curIdx = curIdx + 1

    curIdx = curIdx + 1

    for line in lines[curIdx:]:
        temp = line.split(" ")
        src = int(temp[0]) + 1
        dst = int(temp[1]) + 1
        fout.write(str(src) + "-" + str(dst) + '\n')

    fin.close()
    fout.close()

if __name__ == "__main__":
    transFile(sys.argv[1])
