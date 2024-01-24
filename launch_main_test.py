import argparse
import os

if __name__ == "__main__":
    # parse all incoming arbitrary arguments:
    parser = argparse.ArgumentParser()
    a, b = parser.parse_known_args()

    print("Job", os.environ["SLURM_JOB_ID"], "started.")

    print(a)
    print(b)

    print("Done.")
