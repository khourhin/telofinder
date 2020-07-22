import sys
from Bio import SeqIO
import os.path
import argparse
from pathlib import Path


def output_exists(force):
    """Function to test if the output file already exists, force overwriting the output file or
    exit program.
    """
    file_exists = os.path.isfile("telom_length.csv")
    if file_exists:
        if force:
            print("Replacing the existing file.")
        else:
            sys.exit(
                print(
                    "\n",
                    "Warning!!! A file called 'telom_length.csv' already exists.",
                    "\n",
                    "delete this file before running the script or use the option --force",
                    "\n",
                )
            )


def parse_arguments():
    """Function to parse and reuse the arguments of the command line"""
    parser = argparse.ArgumentParser(
        description="This program determines telomere length at all sequence ends from a single or multiple (multi)fasta file(s)\
        and outputs a csv file called 'telom_length.csv'"
    )
    parser.add_argument(
        "fasta_path",
        help="Path to a single fasta file or to a directory containing multiple fasta files.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Automatically replace the output csv file if present.",
    )
    return parser.parse_args()


def get_strain_name(filename):
    """Function to get the strain name from the path to the fasta file"""
    filepath = Path(filename)
    return filepath.stem


def chr_start_end(genome_fasta, strain):
    """Function to calculate telomere length at all contig ends"""
    print(
        "\n",
        "=================================",
        "\n",
        strain,
        "\n",
        "=================================",
        "\n",
    )

    ## parse the multifasta file and reverse complement each sequence
    for seq_record in SeqIO.parse(genome_fasta, "fasta"):
        revcomp = seq_record.reverse_complement()

        count = 0
        revcount = 0
        offset = 0
        revoffset = 0

        # TODO: the min function can be of help here
        ## set up a limit of 1500 nt at contig ends to browse until we find a telomere sequence
        if len(seq_record.seq) < 1500:
            limit = len(seq_record.seq) - 9
        else:
            limit = 1500

        ## LEFT TELOMERE
        ### estimate the size of the offset sequence before the telomere sequence
        for i in range(0, limit):
            mot = str(seq_record.seq[i : i + 20] + "\n")
            if mot.count("C") + mot.count("A") < 19:
                offset += 1
            else:
                break
        ### estimate the size of the telomere sequence
        for j in range(offset, len(seq_record.seq) - 19):
            mot = str(seq_record.seq[j : j + 20] + "\n")
            if (
                mot.count("C") >= 8
                and mot.count("A") >= 3
                and mot.count("C") + mot.count("A") >= 17
                and "AAAA" not in mot
            ):
                count += 1
            else:
                break

        # TODO: Introduction to the DRY principle. These instructions are the
        # same than for the left telomere, we should so put them in a function
        # and call this function for the left and the right telomere
        ## RIGHT TELOMERE
        ### estimate the size of the offset sequence before the telomere sequence
        for i in range(0, limit):
            revmot = str(revcomp.seq[i : i + 20] + "\n")
            if revmot.count("C") + revmot.count("A") < 19:
                revoffset += 1
            else:
                break
        ### estimate the size of the telomere sequence
        for j in range(revoffset, len(seq_record.seq) - 19):
            revmot = str(revcomp.seq[j : j + 20] + "\n")
            if (
                revmot.count("C") >= 8
                and revmot.count("A") >= 3
                and revmot.count("C") + revmot.count("A") >= 17
                and "AAAA" not in revmot
            ):
                revcount += 1
            else:
                break

        # FIXME: The elif expressions are redundant
        ## definition of telomere and offset lengths
        if count == 0:
            left_tel = 0
            offset = 0
        elif count != 0 and offset != 0:
            left_tel = 20 + count - 3
            offset = offset + 1
        elif count != 0 and offset == 0:
            left_tel = 20 + count - 3

        if revcount == 0:
            right_tel = 0
            revoffset = 0
        elif revcount != 0 and revoffset != 0:
            right_tel = 20 + revcount - 3
            revoffset = revoffset + 1
        elif revcount != 0 and revoffset == 0:
            right_tel = 20 + revcount - 3

        # TODO: Could use fstrings here
        ## stdout
        chrom = seq_record.id
        print(chrom)
        print("---------------------")
        print("left telom length = ", left_tel)
        print("left offset = ", offset)
        print("right telom length = ", right_tel)
        print("right offset = ", revoffset)
        print("\n", "-------------------------------", "\n")

        # TODO: Could use pandas DataFrames here
        ## save the results in a csv file
        file_exists = os.path.isfile("telom_length.csv")
        with open("telom_length.csv", "a") as filout:
            if file_exists:
                filout.write(
                    "{0}\t{1}\tL\t{2}\t{4}\n{0}\t{1}\tR\t{3}\t{5}\n".format(
                        strain, chrom, left_tel, right_tel, offset, revoffset
                    )
                )
            else:
                filout.write(
                    "{0}\t{1}\t{2}\t{3}\t{4}\n{5}\t{6}\tL\t{7}\t{9}\n{5}\t{6}\tR\t{8}\t{10}\n".format(
                        "Strain",
                        "Chromosome",
                        "Contig_side",
                        "Telom_length",
                        "Offset",
                        strain,
                        chrom,
                        left_tel,
                        right_tel,
                        offset,
                        revoffset,
                    )
                )  # file doesn't exist yet, write a header


# function to test if program is run ona single or multiple fasta files
def run_single_or_iterative(fasta_path):

    if Path(fasta_path).is_file():
        print(f"'{fasta_path}' is a file. Running in single mode.")
        strain = get_strain_name(fasta_path)
        chr_start_end(fasta_path, strain)

    if Path(fasta_path).is_dir():
        print(f"'{fasta_path}' is a directory. Running in iterative mode.")

        for ext in ["*.fasta", "*.fas", "*.fa"]:
            for fasta in Path(fasta_path).glob(ext):

                print(fasta)
                strain = get_strain_name(fasta)
                chr_start_end(fasta, strain)


# Main program
if __name__ == "__main__":
    args = parse_arguments()
    output_exists(args.force)
    run_single_or_iterative(args.fasta_path)
