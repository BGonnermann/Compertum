"""Starter program for one specification. Edit decide(); keep the file names as they are.
The job folder holds train.csv and validation.csv next to this file. Open them by these plain names.
Write signals.csv next to this file. The run is complete when signals.csv exists."""
import csv


def read_rows(name):
    with open(name,newline='',encoding='utf-8') as handle: return list(csv.DictReader(handle))


def decide(train,validation):
    """Return one position (0 or 1) for every validation row, in order, using only rows up to that session."""
    return [0 for _ in validation]


def main():
    train=read_rows('train.csv');validation=read_rows('validation.csv')
    positions=decide(train,validation)
    with open('signals.csv','w',newline='',encoding='utf-8') as out:
        out.write('session,position\n')
        for row,position in zip(validation,positions): out.write(f"{row['session']},{int(position)}\n")
    print('signals written',len(positions))


if __name__=='__main__': main()
