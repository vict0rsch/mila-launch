## 🥳 User guide

In a word, use `launch.py` to fill in an sbatch template and submit either
a single job from the command-line, or a list of jobs from a `yaml` file.

Examples:

```bash
# using default job configuration, with script args from the command-line:
$ python launch.py user=$USER logger.do.online=False

# overriding the default job configuration and adding script args:
$ python launch.py --template=template-venv.sh \\
    --venv='~/.venvs/gfn' \\
    --modules='python/3.9 cuda/11.3' \\
    user=$USER logger.do.online=False

# using a yaml file to specify multiple jobs to run:
$ python launch.py --jobs=ViT/v0" --mem=32G
```

### 🤓 How it works

1. All experiment files should be in `config/jobs`
2. You can nest experiment files infinitely, let's say you work on ViTs and call your experiment `vanilla.yaml`
    then you could put your config in `config/jobs/ViT/vanilla.yaml`
3. An experiment file can contain 2 main sections:
    1. `shared:` contains the configuration that will be, you guessed it, shared across jobs (optional).
    2. `jobs:` lists configurations for the SLURM jobs that you want to run. The `shared` configuration will be loaded first, then updated from the `job`'s.
4. Both `shared` and `jobs` dicts contain (optional) sub-sections:
    1. `slurm:` contains what's necessary to parameterize the SLURM job
    2. `script:` contains a dict version of the command-line args to give `main.py`

    ```yaml
    script:
        gflownet:
        optimizer:
            lr: 0.001

    # is equivalent to
    script:
        gflownet.optimizer.lr: 0.001

    # and will be translated to
    python main.py gflownet.optimizer.lr=0.001
    ```

5. Launch the SLURM jobs with `python launch.py --jobs=ViT/vanilla`
    1. `launch.py` knows to look in `config/jobs/` and add `.yaml` (but you can write `.yaml` yourself)
    2. You can overwrite anything from the command-line: the command-line arguments have the final say and will overwrite all the jobs' final dicts.
        Run `python launch.py -h` to see all the known args.
    3. You can also override `script` params from the command-line: unknown arguments will be given as-is to `main.py`.
        For instance `python launch.py --jobs=ViT/vanilla --mem=32G model.some_param=value` is valid
6. `launch.py` loads a template (`config/templates/conda.sh`) by default, and fills it with the arguments specified,
    then writes the filled template in the folder specified by `launch.conf.yaml:sbatch_files_root`
    with the current datetime and experiment file name.
7. `launch.py` executes `sbatch` in a subprocess to execute the filled template above
8. A summary yaml is also created there, with the exact experiment file and appended `SLURM_JOB_ID`s returned by `sbatch`

### 📝 Case-study

Let's study the following example:

```text
$ python launch.py foo.bar=21 --jobs=example-jobs --cpus=1
🗂  Using jobs file: ./config/jobs/example-jobs.yaml

💥 Git warnings:
• `--git_checkout` not provided. Using current branch: main
• Your repo contains uncommitted changes. They will *not* be available when cloning happens within the job.
• You are 4 commits ahead of origin/main
Continue anyway? [y/N] y

🚨 Submit 3 jobs? [y/N] y


✅ Submitted batch job 4058583
🏷  Created $SCRATCH/mila-launch/mila-launch/sbatch_files/example-jobs_4058583_2024-01-24_14-00-50.sbatch
📝 Job output file will be: $SCRATCH/mila-launch/logs/slurm/mila-launch-4058583.out

✅ Submitted batch job 4058584
🏷  Created $SCRATCH/mila-launch/mila-launch/sbatch_files/example-jobs_4058584_2024-01-24_14-00-50.sbatch
📝 Job output file will be: $SCRATCH/mila-launch/logs/slurm/mila-launch-4058584.out

✅ Submitted batch job 4058585
🏷  Created $SCRATCH/mila-launch/mila-launch/sbatch_files/example-jobs_4058585_2024-01-24_14-00-50.sbatch
📝 Job output file will be: $SCRATCH/mila-launch/logs/slurm/mila-launch-4058585.out

🚀 Submitted job 3/3
Created summary YAML in /network/scratch/s/schmidtv/mila-launch/mila-launch/sbatch_files/example-jobs_2024-01-24_14-00-50.yaml
All jobs submitted: 4058583 4058584 4058585
```

Say the file `./config/jobs/example-jobs.yaml` contains:

```yaml
# Contents of ./config/jobs/example-jobs.yaml

{yaml_example}
```

Then the launch command-line ^ will execute 3 jobs with the following configurations:

```bash
python main.py foo.bar=21 user=$USER +experiments=neurips23/crystal-comp-sg-lp.yaml gflownet=flowmatch gflownet.optimizer.lr=0.0001

python main.py foo.bar=21 user=$USER +experiments=neurips23/crystal-comp-sg-lp.yaml gflownet=flowmatch gflownet.optimizer.lr=0.0001 gflownet.policy.backward=None

python main.py foo.bar=21 user=$USER +experiments=neurips23/crystal-comp-sg-lp.yaml gflownet=trajectorybalance gflownet.optimizer.lr=0.0001
```

And their SLURM configuration will be similar as the `shared.slurm` params, with the following differences:

1. The second job will have `partition: unkillable` instead of the default (`long`).
2. They will all have `1` `cpu` of the default (`2`) because the `--cpus=1` command-line
    argument overrides everything.

## Git

By default, the following actions and checks are performed:

* If you set the `code_dir` to `$SLURM_TMPDIR`, then the git repo will be cloned there.

    * In that case, you can also set `git_checkout` to a branch or commit to checkout.
        If you don't, the current branch will be used and you'll be prompted for confirmation.

* The git repo is checked for uncommitted changes. If there are any, you'll be prompted for confirmation.
* The git repo is checked for commits ahead or behind of the remote. If there are any, you'll be prompted for confirmation.

You can disable all of these checks with `--allow_unclean_repo` and `--allow_no_checkout`
or by changing the defaults in `config/templates/launch.conf.yaml`.

## Updating the launcher

When updating the launcher, you should:

1. Update this markdown text **in launch.py:HELP** (do not edit this `LAUNCH.md`)
2. Run `$ python mila/launch.py --help-md > LAUNCH.md` to update this `LAUNCH.md` from the new `launch.py:HELP` text, new flags etc.