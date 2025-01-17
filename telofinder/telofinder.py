import sys
from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq
import os.path
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from collections import Counter
import pybedtools
from multiprocessing import Pool
from functools import partial
import pysam

from telofinder.plotting import plot_telom


def get_strain_name(filename):
    """Function to get the strain name from the name of the fasta file

    :param filename: path of fasta file
    :return: sequence name
    """
    filepath = Path(filename)
    return filepath.stem


def sliding_window(sequence, start, end, size):
    """Apply a sliding window of length = size to a sequence from start to end

    :param sequence: fasta sequence
    :param start: starting coordinate of the sequence
    :param end: ending coordinate of the sequence
    :param size: size of the sliding window
    :return: the coordinate and the sequence of the window
    """
    if size > len(sequence):
        sys.exit("The window size must be smaller than the sequence")
    for i in range(start, end - (size - 1)):
        window = str(sequence[i : i + size])
        yield i, window


def base_compos(sequence, base):
    """Counts the number of a given base in a sequence

    :param sequence: fasta sequence
    :param base: base to count in the sequence
    :return: the number of that base in the sequence
    """
    count = Counter(sequence)[base]
    return count


def count_polynuc_occurence(sub_window, polynucleotide_list):
    """Define presence of polynucleotide in the window.

    :param sub_window: the sequence of a sub_window
    :param polynuleotide_list: a list of polynucleotides. Note that all polynucleotides must be of the same size
    :return: a boolean for the presence of the sub_window in the polynucleotide list
    """
    if sub_window in polynucleotide_list:
        return 1
    else:
        return 0


def get_polynuc(window, polynucleotide_list):
    """get the propbortion of polynuceotides in the window

    :param window: sliding window
    :param polynucleotide_list: a list of polynucleotides. Note that all polynucleotides must be of the same size
    :return: total polynucleotide proportion in the sliding window
    """
    sum_dinuc = 0
    for _, sub_window in sliding_window(window.upper(), 0, len(window), 2):
        sum_dinuc += count_polynuc_occurence(sub_window, polynucleotide_list)
    freq_dinuc = sum_dinuc / (len(window) - 1)
    return freq_dinuc


def get_entropy(window):
    """Calculate the entropy of the window DNA sequence

    :param window: sliding window
    :return: entropy value of the sequence window
    """
    entropy = 0

    for base in ["A", "T", "G", "C"]:
        if window.upper().count(base) == 0:
            proba_base = 0
        else:
            freq_base = window.upper().count(base) / len(window)
            proba_base = -(freq_base * np.log(freq_base))

        entropy += proba_base

    return entropy


def compute_metrics(window, polynucleotide_list=["AC", "CA", "CC"]):
    """Compute entropy and polynucleotide proportion in the sequence window

    :param window: sliding window
    :param polynucleotide_list: a list of polynucleotides, default value is ["AC", "CA", "CC"]
    :return: a dictionary of entropy and polynucleotide proportion of the sequence window
    """

    # polynucleotide_list_chlamy=["AA", "AC", "CC", "CT", "TC", "TA"]

    metrics = {
        "entropy": get_entropy(window),
        "polynuc": get_polynuc(window, polynucleotide_list),
        # "skew": get_skewness(window),
        # "cg_skew": get_cg_skew(window),
        # "skew_norm": get_norm_freq_base(window),
        # "chi2": get_chi2(window),
        # "freq_norm_T": get_freq_norm_T(window),
        # "freq_norm_C": get_freq_norm_C(window),
        # "max_diff": get_add_freq_diff(window),
    }

    return metrics


def get_consecutive_groups(df_chrom):
    """From the raw dataframe get start and end of each telomere window.
    Applied to detect start and end of telomere in nucleotide positions.
    """
    df = df_chrom.reset_index()
    chrom_groups = {}
    for strand in ["W", "C"]:
        nums = list(df.query("(level_3==@strand) and (predict_telom==1)").level_2)
        nums = sorted(set(nums))
        gaps = [[s, e] for s, e in zip(nums, nums[1:]) if s + 1 < e]
        edges = iter(nums[:1] + sum(gaps, []) + nums[-1:])
        chrom_groups[strand] = list(zip(edges, edges))

        # [{"start":x, "end":y} for x, y in b["W"]]

    return chrom_groups


def classify_telomere(interval_chrom, chrom_len):
    """From a list of tuples obtained from get_consecutive_groups, identify if
    interval corresponds to terminal or interal telomere
    """
    classif_dict_list = []

    interval_W = interval_chrom["W"][:]
    if interval_W == []:
        classif_dict_list.append(
            {"start": None, "end": None, "side": "Left", "type": "term"}
        )
        classif_dict_list.append(
            {"start": None, "end": None, "side": "Left", "type": "intern"}
        )
    elif min(interval_W)[0] == 0:
        classif_dict_list.append(
            {
                "start": 0 + 1,
                "end": min(interval_W)[1] + 1 + 19,
                "side": "Left",
                "type": "term",
            }
        )
        interval_W.remove(min(interval_W))
        for interval in interval_W:
            classif_dict_list.append(
                {
                    "start": interval[0] + 1,
                    "end": interval[1] + 1 + 19,
                    "side": "Left",
                    "type": "intern",
                }
            )
    else:
        for interval in interval_W:
            classif_dict_list.append(
                {
                    "start": interval[0] + 1,
                    "end": interval[1] + 1 + 19,
                    "side": "Left",
                    "type": "intern",
                }
            )

    interval_C = interval_chrom["C"][:]
    if interval_C == []:
        classif_dict_list.append(
            {"start": None, "end": None, "side": "Right", "type": "term"}
        )
        classif_dict_list.append(
            {"start": None, "end": None, "side": "Right", "type": "intern"}
        )
    elif max(interval_C)[1] == (chrom_len - 1):
        classif_dict_list.append(
            {
                "start": max(interval_C)[0] + 1 - 19,
                "end": max(interval_C)[1] + 1,
                "side": "Right",
                "type": "term",
            }
        )
        interval_C.remove(max(interval_C))
        for interval in interval_C:
            classif_dict_list.append(
                {
                    "start": interval[0] + 1 - 19,
                    "end": interval[1] + 1,
                    "side": "Right",
                    "type": "intern",
                }
            )

    else:
        for interval in interval_C:
            classif_dict_list.append(
                {
                    "start": interval[0] + 1 - 19,
                    "end": interval[1] + 1,
                    "side": "Right",
                    "type": "intern",
                }
            )

    return classif_dict_list


def export_results(
    raw_df,
    telom_df,
    merged_telom_df,
    raw,
    outdir="telofinder_results",
):
    """Produce output table files"""
    outdir = Path(outdir)
    try:
        outdir.mkdir()
    except FileExistsError:
        pass

    telom_df.to_csv(outdir / "telom_df.csv", index=False)
    merged_telom_df.to_csv(outdir / "merged_telom_df.csv", index=False)

    bed_df = telom_df[["chrom", "start", "end", "type"]].copy()
    bed_df.dropna(inplace=True)
    bed_df.to_csv(outdir / "telom.bed", sep="\t", header=None, index=False)

    merged_bed_df = merged_telom_df[["chrom", "start", "end", "type"]].copy()
    merged_bed_df.dropna(inplace=True)
    merged_bed_df.to_csv(
        outdir / "telom_merged.bed", sep="\t", header=None, index=False
    )

    if raw:
        raw_df.to_csv(outdir / "raw_df.csv", index=True)


def run_on_single_seq(seq_record, strain, polynuc_thres, entropy_thres, nb_scanned_nt):
    seqW = str(seq_record.seq)
    revcomp = seq_record.reverse_complement()
    seqC = str(revcomp.seq)

    if nb_scanned_nt == -1:
        limit_seq = len(seqW)
    else:
        limit_seq = min(nb_scanned_nt, len(seqW))

    seq_dict_W = {}
    seq_dict_C = {}

    for i, window in sliding_window(seqW, 0, limit_seq, 20):
        seq_dict_W[(strain, seq_record.name, i, "W")] = compute_metrics(window)

    df_W = pd.DataFrame(seq_dict_W).transpose()

    for i, window in sliding_window(seqC, 0, limit_seq, 20):
        seq_dict_C[
            (strain, seq_record.name, (len(seqC) - i - 1), "C")
        ] = compute_metrics(window)

    df_C = pd.DataFrame(seq_dict_C).transpose()

    df_chro = pd.concat([df_W, df_C])

    df_chro.loc[
        (df_chro["entropy"] < entropy_thres) & (df_chro["polynuc"] > polynuc_thres),
        "predict_telom",
    ] = 1.0

    df_chro["predict_telom"].fillna(0, inplace=True)

    telo_groups = get_consecutive_groups(df_chro)
    telo_list = classify_telomere(telo_groups, len(seq_record.seq))
    telo_df = pd.DataFrame(telo_list)
    telo_df["chrom"] = seq_record.name
    telo_df["chrom_size"] = len(seq_record.seq)

    if telo_df["start"].isnull().sum() == 4:
        telo_df_merged = telo_df.copy()
    else:
        bed_df = telo_df[["chrom", "start", "end", "type"]].copy()
        bed_df.dropna(inplace=True)
        bed_df = bed_df.astype({"start": int, "end": int})
        bed_file = pybedtools.BedTool().from_dataframe(bed_df)
        bed_sort = bed_file.sort()
        bed_merge = bed_sort.merge(d=20)
        bed_df_merged = bed_merge.to_dataframe()
        telo_df_merged = pd.merge(
            bed_df_merged,
            telo_df.dropna()[["chrom", "side", "type", "start", "chrom_size"]],
            on=["chrom", "start"],
            how="left",
        )
        telo_df_merged.loc[
            telo_df_merged.end > len(seq_record.seq) - 20, "type"
        ] = "term"
        telo_df_merged.loc[telo_df_merged.start < 20, "type"] = "term"

    telo_df_merged["strain"] = strain
    telo_df_merged = telo_df_merged[
        ["strain", "chrom", "side", "type", "start", "end", "chrom_size"]
    ]

    telo_df["strain"] = strain
    telo_df = telo_df[["strain", "chrom", "side", "type", "start", "end"]]

    print(f"chromosome {seq_record.name} done")

    return (df_chro, telo_df, telo_df_merged)


def run_on_single_fasta(
    fasta_path, polynuc_thres, entropy_thres, nb_scanned_nt, threads
):
    """Run the telomere detection algorithm on a single fasta file

    :param fasta_path: path to fasta file
    :return: a tuple of df, telo_df and telo_df_merged
    """
    strain = get_strain_name(fasta_path)
    print("\n", "-------------------------------", "\n")
    print(f"file {strain} executed")

    partial_ross = partial(
        run_on_single_seq,
        strain=strain,
        polynuc_thres=polynuc_thres,
        entropy_thres=entropy_thres,
        nb_scanned_nt=nb_scanned_nt,
    )

    with Pool(threads) as p:

        results = p.map(partial_ross, SeqIO.parse(fasta_path, "fasta"))

    raw_df = pd.concat([r[0] for r in results])

    telo_df = pd.concat([r[1] for r in results])
    telo_df["len"] = telo_df["end"] - telo_df["start"] + 1
    telo_df = telo_df.astype({"start": "Int64", "end": "Int64", "len": "Int64"})

    telo_df_merged = pd.concat([r[2] for r in results])
    telo_df_merged["len"] = telo_df_merged["end"] - telo_df_merged["start"] + 1
    telo_df_merged = telo_df_merged.astype(
        {"start": "Int64", "end": "Int64", "len": "Int64", "chrom_size": "Int64"}
    )
    telo_df_merged = telo_df_merged[
        ["strain", "chrom", "side", "type", "start", "end", "len", "chrom_size"]
    ]

    return raw_df, telo_df, telo_df_merged


def run_on_fasta_dir(
    fasta_dir_path, polynuc_thres, entropy_thres, nb_scanned_nt, threads
):
    """Run iteratively the telemore detection algorithm on all fasta files in a directory

    :param fasta_dir: path to fasta directory
    :return: a tuple of df, telo_df and telo_df_merged
    """
    raw_dfs = []
    telom_dfs = []
    merged_telom_dfs = []

    for ext in ["*.fasta", "*.fas", "*.fa", "*.fsa"]:
        for fasta in fasta_dir_path.glob(ext):

            raw_df, telom_df, merged_telom_df = run_on_single_fasta(
                fasta, polynuc_thres, entropy_thres, nb_scanned_nt, threads
            )
            raw_dfs.append(raw_df)
            telom_dfs.append(telom_df)
            merged_telom_dfs.append(merged_telom_df)

    total_raw_df = pd.concat(raw_dfs)
    total_telom_df = pd.concat(telom_dfs)
    total_merged_telom_df = pd.concat(merged_telom_dfs)

    return total_raw_df, total_telom_df, total_merged_telom_df


def get_telomeric_reads(bam_file, telo_df_merged, outdir="telofinder_telomeric_reads"):
    """Extract telomeric reads from a bam file corresponding to telomere detected
    and reported in telo_df_merged

    :param bam_file: An indexed bam alignment file.  :param telo_df_merged:
    Merged DataFrame with telomeric informations (from one of the run_telofinder
    functions)
    """

    outdir = Path(outdir)
    outdir.mkdir()

    stats = []

    for chro, start, end in telo_df_merged.apply(
        lambda x: (x.chrom, x.start, x.end), axis=1
    ):

        out_sam = outdir / f"telomeric_reads_{chro}_{start}_{end}.sam"
        out_fas = outdir / f"telomeric_reads_{chro}_{start}_{end}.fas"

        with open(out_sam, "w") as sam:
            with open(out_fas, "w") as fas:
                with pysam.AlignmentFile(bam_file) as bam:
                    for rd in bam.fetch(chro, start, end):

                        if rd.mapq > 0:

                            sam.write(str(rd))
                            fas.write(f">{rd.qname}\n{rd.query_sequence}\n")

                            stats.append(
                                {
                                    "bam": Path(bam_file).stem,
                                    "chro": chro,
                                    "start": start,
                                    "end": end,
                                    "read_len": len(rd.query_sequence),
                                }
                            )

        df, telo_df, merged_telo_df = run_on_single_fasta(
            out_fas, 0.8, 0.8, 8000, threads=4
        )
    return merged_telo_df


