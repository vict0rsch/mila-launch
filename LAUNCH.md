# 🤝 Mila Launch tool help

## 💻 Command-line help

In the following, `$root` refers to the root of the current repository.

```sh
usage: launch.py [-h] [--help-md] [--job_name JOB_NAME] [--outdir OUTDIR]
                 [--cpus_per_task CPUS_PER_TASK] [--mem MEM] [--gres GRES]
                 [--partition PARTITION] [--time TIME] [--modules MODULES]
                 [--conda_env CONDA_ENV] [--venv VENV] [--template TEMPLATE]
                 [--code_dir CODE_DIR] [--git_checkout GIT_CHECKOUT]
                 [--jobs JOBS] [--dry_run] [--verbose] [--force]
                 [--command COMMAND] [--script_path SCRIPT_PATH]
                 [--sbatch_files_root SBATCH_FILES_ROOT]
                 [--allow_unclean_repo] [--allow_no_checkout]
                 [--clone_as_https]

optional arguments:
  -h, --help            show this help message and exit
  --help-md             Show an extended help message as markdown. Can be
                        useful to overwrite LAUNCH.md with `$ python
                        mila/launch.py --help-md > LAUNCH.md`
  --job_name JOB_NAME   slurm job name to show in squeue. Defaults to mila-
                        launch
  --outdir OUTDIR       where to write the slurm .out file. Defaults to
                        $SCRATCH/$repoName/logs/slurm
  --cpus_per_task CPUS_PER_TASK
                        number of cpus per SLURM task. Defaults to 1
  --mem MEM             memory per node (e.g. 32G). Defaults to 16G
  --gres GRES           gres per node (e.g. gpu:1). Defaults to
  --partition PARTITION
                        slurm partition to use for the job. Defaults to
                        unkillable
  --time TIME           wall clock time limit (e.g. 2-12:00:00). See:
                        https://slurm.schedmd.com/sbatch.html#OPT_time
                        Defaults to
  --modules MODULES     string after 'module load'. Defaults to
  --conda_env CONDA_ENV
                        conda environment name. Defaults to base
  --venv VENV           path to venv (without bin/activate). Defaults to
  --template TEMPLATE   path to sbatch template. Defaults to conda.sh
  --code_dir CODE_DIR   cd before running main.py. Defaults to $SLURM_TMPDIR
  --git_checkout GIT_CHECKOUT
                        Branch or commit to checkout before running the code.
                        This is only used if --code_dir='$SLURM_TMPDIR'. If
                        not specified, the current branch is used. Defaults to
  --jobs JOBS           jobs (nested) file name in external/jobs (with or
                        without .yaml). Or an absolute path to a yaml file
                        anywhere Defaults to
  --dry_run             Don't run just, show what it would have run. Defaults
                        to False
  --verbose             print templated sbatch after running it. Defaults to
                        False
  --force               Skip user confirmation. Defaults to False
  --command COMMAND     Command to run. Defaults to python
  --script_path SCRIPT_PATH
                        Script to run by command. Defaults to
                        launch_main_demo.py
  --sbatch_files_root SBATCH_FILES_ROOT
                        Where to write the sbatch files. Defaults to
                        $SCRATCH/mila-launch/$repoName/sbatch_files
  --allow_unclean_repo  Raise an error if the git repo is not clean. Defaults
                        to False
  --allow_no_checkout   Warn if no git checkout is provided. Defaults to True
  --clone_as_https      Clone the repo as https instead of ssh. Defaults to
                        True

```

## 🎛️ Default values

```yaml
allow_no_checkout  : True
allow_unclean_repo : False
clone_as_https     : True
code_dir           : $SLURM_TMPDIR
command            : python
conda_env          : base
cpus_per_task      : 1
dry_run            : False
force              : False
git_checkout       : ""
gres               : ""
job_name           : mila-launch
jobs               : ""
mem                : 16G
modules            : ""
outdir             : $SCRATCH/$repoName/logs/slurm
partition          : unkillable
sbatch_files_root  : $SCRATCH/mila-launch/$repoName/sbatch_files
script_args        : ""
script_path        : launch_main_demo.py
template           : conda.sh
time               : ""
venv               : ""
verbose            : False
```
# 🥳 User guide

In a word, use `launch.py` to fill in an sbatch template and submit either
a single job from the command-line, or a list of jobs from a `yaml` file.

Examples:

```bash
# using default job configuration, with script args from the command-line:
$ python launch.py user=$USER logger.do.online=False
# creates an sbatch files with, amongst other things: $ python main.py user=$USER logger.do.online=False

# overriding the default job configuration and adding script args:
$ python launch.py --template=venv.sh --modules='python/3.9 cuda/11.3' --cpus=3 user=$USER logger.do.online=False
# creates an sbatch file with a different config and still $ python main.py user=$USER logger.do.online=False

# using a yaml file to specify multiple jobs to run:
$ python launch.py --jobs=ViT/v0" --mem=32G
```

In general:

* Known args are used to configure the job (SLURM resources, module loading and git cloning)
* Unknown args are passed down to the script you want to execute in that job

Read the known args in `config/templates/launch.conf.yaml`

## 🤓 How job files work

1. All job configuration files should be in `config/jobs/`
2. You can nest experiment files infinitely, let's say you work on ViTs and call your experiment `vanilla.yaml` then you could put your config in `config/jobs/ViT/vanilla.yaml`
3. An experiment file can contain 2 main sections:
    1. `shared:` contains the configuration that will be, you guessed it, shared across jobs (optional).
    2. `jobs:` lists configurations for the SLURM jobs that you want to run.
       1. The `shared` configuration will be loaded first, then updated from the `job`'s.
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
    # python main.py gflownet.optimizer.lr=0.001
    ```

5. Launch the SLURM jobs with `python launch.py --jobs=ViT/vanilla`
    1. `launch.py` knows to look in `config/jobs/` and add `.yaml`
       1. but you can write `.yaml` yourself
       2. and you can pass a path to a file out of there if you want to
    2. You can overwrite anything from the command-line: **the command-line arguments have the final say** and will overwrite all the jobs' final dicts.
       1. Run `python launch.py -h` to see all the known args.
    3. You can also override `script` params from the command-line: unknown (to `launch.py`) arguments will be given as-is to `main.py`.
       1. For instance `python launch.py --jobs=ViT/vanilla --mem=32G model.some_param=value` is valid
6. `launch.py` loads a template (`config/templates/conda.sh`) by default, and fills it with the arguments specified, then writes the filled template in the folder specified by `launch.conf.yaml:sbatch_files_root` with the current datetime, experiment file name **and `SLURM_JOB_ID`** (if you didn't use `--dry_run`).
7. `launch.py` executes `sbatch` in a subprocess to execute the filled template above
8. A summary yaml is also created containing:
   1. The launch command-line executed
   2. The list of submitted job ids
   3. The list of SLURM output files


## Git

By default, the following actions and checks are performed:

* If you set the `code_dir` to `$SLURM_TMPDIR`, then the git repo will be cloned there.

    * In that case, you can also set `git_checkout` to a branch or commit to checkout.
        If you don't, the current branch will be used and you'll be prompted for confirmation.

* The git repo is checked for uncommitted changes. If there are any, you'll be prompted for confirmation.
* The git repo is checked for commits ahead or behind of the remote. If there are any, you'll be prompted for confirmation.

You can disable all of these checks with `--allow_unclean_repo` and `--allow_no_checkout`
or by changing the defaults in `config/templates/launch.conf.yaml`.

## 📝 Case-study

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

shared:
  # job params
  slurm:
    template: conda.sh # which template to use in `config/templates/` or path to a separate template file
    modules: anaconda/3 cuda/11.3 # string of the modules to load
    conda_env: gflownet # name of the environment
    code_dir: $SLURM_TMPDIR # needed if you have multiple repos, eg for dev and production
    gres: gpu:1 # slurm gres
    mem: 16G # node memory
    cpus_per_task: 2 # task cpus

  # main.py params
  script:
    user: $USER
    +experiments: neurips23/crystal-comp-sg-lp.yaml
    gflownet:
      __value__: flowmatch # special entry if you want to see `gflownet=flowmatch`
    optimizer:
      lr: 0.0001 # will be translated to `gflownet.optimizer.lr=0.0001`

# list of slurm jobs to execute
jobs:
  - {} # empty dictionary = just run with the shared params
  - slurm: # change this job's slurm params
      partition: unkillable
    script: # change this job's script params
      gflownet:
        policy:
          backward: null
  - script:
      gflownet:
        __value__: trajectorybalance # again, special entry to see `gflownet=trajectorybalance`
        hidden_dim: 128 # adds `gflownet.hidden_dim=128` to the command-line
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

## Updating the launcher

When updating the launcher, you should:

1. Update this markdown text **in launch.py:HELP** (do not edit this `LAUNCH.md`)
2. Run `$ python mila/launch.py --help-md > LAUNCH.md` to update this `LAUNCH.md` from the new `launch.py:HELP` text, new flags etc.
