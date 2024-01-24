# 🤝 Mila Launch tool help

## 💻 Command-line help

In the following, `$root` refers to the root of the current repository.

```sh
usage: launch.py [-h] [--help-md] [--job_name JOB_NAME] [--outdir OUTDIR]
                 [--cpus_per_task CPUS_PER_TASK] [--mem MEM] [--gres GRES]
                 [--partition PARTITION] [--time TIME] [--modules MODULES]
                 [--conda_env CONDA_ENV] [--venv VENV] [--template TEMPLATE]
                 [--code_dir CODE_DIR] [--git_checkout GIT_CHECKOUT]
                 [--jobs JOBS] [--dry-run] [--verbose] [--force]
                 [--command COMMAND] [--script SCRIPT]
                 [--sbatch_files_root SBATCH_FILES_ROOT]
                 [--prevent_unclean_repo] [--warn_no_checkout]
                 [--clone_as_https]

options:
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
  --code_dir CODE_DIR   cd before running main.py. Defaults to $SLURM_TMP_DIR
  --git_checkout GIT_CHECKOUT
                        Branch or commit to checkout before running the code.
                        This is only used if --code_dir='$SLURM_TMPDIR'. If
                        not specified, the current branch is used. Defaults to
  --jobs JOBS           jobs (nested) file name in external/jobs (with or
                        without .yaml). Or an absolute path to a yaml file
                        anywhere Defaults to
  --dry-run             Don't run just, show what it would have run. Defaults
                        to False
  --verbose             print templated sbatch after running it. Defaults to
                        False
  --force               Skip user confirmation. Defaults to False
  --command COMMAND     Command to run. Defaults to python
  --script SCRIPT       Script to run by command. Defaults to main.py
  --sbatch_files_root SBATCH_FILES_ROOT
                        Where to write the sbatch files. Defaults to
                        $SCRATCH/mila-launch/$repoName/sbatch_files
  --prevent_unclean_repo
                        Raise an error if the git repo is not clean. Defaults
                        to True
  --warn_no_checkout    Warn if no git checkout is provided. Defaults to True
  --clone_as_https      Clone the repo as https instead of ssh. Defaults to
                        True

```

## 🎛️ Default values

```yaml
dry-run              : False
force                : False
prevent_unclean_repo : True
sbatch_files_root    : $SCRATCH/mila-launch/$repoName/sbatch_files
verbose              : False
warn_no_checkout     : True
clone_as_https       : True
code_dir             : $SLURM_TMP_DIR
command              : python
conda_env            : base
cpus_per_task        : 1
git_checkout         : ""
gres                 : ""
job_name             : mila-launch
jobs                 : ""
script_args          : ""
mem                  : 16G
modules              : ""
outdir               : $SCRATCH/$repoName/logs/slurm
partition            : unkillable
script               : main.py
template             : conda.sh
time                 : ""
venv                 : ""
```

## 🥳 User guide

In a word, use `launch.py` to fill in an sbatch template and submit either
a single job from the command-line, or a list of jobs from a `yaml` file.

Examples:

```bash
# using default job configuration, with script args from the command-line:
$ python launch.py user=$USER logger.do.online=False

# overriding the default job configuration and adding script args:
$ python launch.py --template=template-venv.sh \
    --venv='~/.venvs/gfn' \
    --modules='python/3.9 cuda/11.3' \
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
$ python launch.py --jobs=ViT/vanilla --mem=64G

🗂 Using run file: ./external/jobs/crystals/explore-losses.yaml

🚨 Submit 3 jobs? [y/N] y

  🏷  Created ./external/launched_sbatch_scripts/example_20230613_194430_0.sbatch
  ✅  Submitted batch job 3301572

  🏷  Created ./external/launched_sbatch_scripts/example_20230613_194430_1.sbatch
  ✅  Submitted batch job 3301573

  🏷  Created ./external/launched_sbatch_scripts/example_20230613_194430_2.sbatch
  ✅  Submitted batch job 3301574


🚀 Submitted job 3/3
Created summary YAML in ./external/launched_sbatch_scripts/example_20230613_194430.yaml
All jobs submitted: 3301572 3301573 3301574
```

Say the file `./external/jobs/crystals/explore-losses.yaml` contains:

```yaml
# Contents of external/jobs/crystals/explore-losses.yaml

# Shared section across jobs
# $root is a special string that resolves to the root of the repo
shared:
  # job params
  slurm:
    template: conda.sh # which template to use in `config/templates/` or path to a separate template file
    modules: anaconda/3 cuda/11.3 # string of the modules to load
    conda_env: gflownet # name of the environment
    code_dir: $root # needed if you have multiple repos, eg for dev and production
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
python main.py user=$USER +experiments=neurips23/crystal-comp-sg-lp.yaml gflownet=flowmatch gflownet.optimizer.lr=0.0001

python main.py user=$USER +experiments=neurips23/crystal-comp-sg-lp.yaml gflownet=flowmatch gflownet.optimizer.lr=0.0001 gflownet.policy.backward=None

python main.py user=$USER +experiments=neurips23/crystal-comp-sg-lp.yaml gflownet=trajectorybalance gflownet.optimizer.lr=0.0001
```

And their SLURM configuration will be similar as the `shared.slurm` params, with the following differences:

1. The second job will have `partition: unkillable` instead of the default (`long`).
2. They will all have `64G` of memory instead of the default (`32G`) because the `--mem=64G` command-line
    argument overrides everything.

## Updating the launcher

When updating the launcher, you should:

1. Update this markdown text **in launch.py:HELP** (do not edit this `LAUNCH.md`)
2. Run `$ python mila/launch.py --help-md > LAUNCH.md` to update this `LAUNCH.md` from the new `launch.py:HELP` text, new flags etc.
