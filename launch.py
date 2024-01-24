import datetime
import re
import sys
from argparse import ArgumentParser
from copy import deepcopy
from os import popen
from os.path import expandvars
from pathlib import Path
from textwrap import dedent

from git import Repo
from git.exc import GitCommandError
from yaml import safe_load

ROOT = Path(__file__).resolve().parent

GIT_WARNING = True

HELP = dedent(
    """
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

    {yaml_example}
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
    """.format(
        yaml_example="\n".join(
            [
                # need to indend those lines because of dedent()
                "    " + l if i else l  # first line is already indented
                for i, l in enumerate(
                    (ROOT / "config/jobs/example-jobs.yaml")
                    .read_text()
                    .splitlines()[6:]  # ignore first lines which are just comments
                )
            ]
        )
    )
)


def resolve_env_vars(string):
    """
    Resolves environment variables in a string.

    Known special variables:
    - $root: resolves to the root of the current repository
    - $repoName: resolves to the name of the current repository

    Args:
        string (str): The string to resolve

    Returns:
        str: resolved string
    """
    candidate = string.replace("$root", str(ROOT)).replace("$repoName", ROOT.name)
    if "$" in candidate:
        candidate = expandvars(candidate)
    return candidate


def resolve(path):
    """
    Resolves a path with environment variables and user expansion.
    All paths will end up as absolute paths.

    Args:
        path (str | Path): The path to resolve

    Returns:
        Path: resolved path
    """
    if path is None:
        return None
    path = str(path).replace("$root", str(ROOT))
    return Path(resolve_env_vars(path)).expanduser().resolve()


def now_str():
    """
    Returns a string with the current date and time.
    Eg: "20210923_123456"

    Returns:
        str: current date and time
    """
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def load_jobs(yaml_path):
    """
    Loads a yaml file with run configurations and turns it into a list of jobs.

    Example yaml file:

    ```
    shared:
      slurm:
        gres: gpu:1
        mem: 16G
        cpus_per_task: 2
      script:
        user: $USER
        +experiments: neurips23/crystal-comp-sg-lp.yaml
        gflownet:
          __value__: tranjectorybalance

    jobs:
    - {}
    - script:
        gflownet:
            __value__: flowmatch
            policy:
                backward: null
    - slurm:
        partition: main
      script:
        gflownet.policy.backward: null
        gflownet: flowmatch
    ```

    Args:
        yaml_path (str | Path): Where to fine the yaml file

    Returns:
        list[dict]: List of run configurations as dicts
    """
    if yaml_path is None:
        return []
    with open(yaml_path, "r") as f:
        jobs_config = safe_load(f)

    shared_slurm = jobs_config.get("shared", {}).get("slurm", {})
    shared_script = jobs_config.get("shared", {}).get("script", {})
    jobs = []
    for job_dict in jobs_config["jobs"]:
        job_slurm = deep_update(shared_slurm, job_dict.get("slurm", {}))
        job_script = deep_update(shared_script, job_dict.get("script", {}))
        job_dict["slurm"] = job_slurm
        job_dict["script"] = job_script
        jobs.append(job_dict)
    return jobs


def find_jobs_conf(conf):
    """
    TODO: docstring
    """
    local_out_dir = resolve(resolve_env_vars(conf["sbatch_files_root"]))
    if not conf.get("jobs"):
        return None, local_out_dir / "_other_"

    if resolve(conf["jobs"]).is_file():
        assert conf["jobs"].endswith(".yaml") or conf["jobs"].endswith(
            ".yml"
        ), "jobs file must be a yaml file"
        jobs_conf_path = resolve(conf["jobs"])
        local_out_dir = local_out_dir / jobs_conf_path.parent.name
    else:
        if conf["jobs"].endswith(".yaml"):
            conf["jobs"] = conf["jobs"][:-5]
        if conf["jobs"].endswith(".yml"):
            conf["jobs"] = conf["jobs"][:-4]
        if conf["jobs"].startswith("external/"):
            conf["jobs"] = conf["jobs"][9:]
        if conf["jobs"].startswith("jobs/"):
            conf["jobs"] = conf["jobs"][5:]
        yamls = [
            str(y) for y in (ROOT / "config" / "jobs").glob(f"{conf['jobs']}.y*ml")
        ]
        if len(yamls) == 0:
            raise ValueError(
                f"Could not find {conf['jobs']}.y(a)ml in ./external/jobs/"
            )
        if len(yamls) > 1:
            print(">>> Warning: found multiple matches:\n  •" + "\n  •".join(yamls))
        jobs_conf_path = Path(yamls[0])
        local_out_dir = local_out_dir / jobs_conf_path.parent.relative_to(
            ROOT / "config" / "jobs"
        )
    print("🗂  Using jobs file: ./" + str(jobs_conf_path.relative_to(Path.cwd())))
    print()
    return jobs_conf_path, local_out_dir


def quote(value):
    v = str(value)
    v = v.replace("(", r"\(").replace(")", r"\)")
    if " " in v or "=" in v:
        if '"' not in v:
            v = f'"{v}"'
        elif "'" not in v:
            v = f"'{v}'"
        else:
            raise ValueError(f"Cannot quote {value}")
    return v


def script_dict_to_script_args_str(script_dict, is_first=True, nested_key=""):
    """
    Recursively turns a dict of script args into a string of main.py args
    as `nested.key=value` pairs

    Args:
        script_dict (dict): script dictionary of args
        previous_str (str, optional): base string to append to. Defaults to "".
    """
    if not isinstance(script_dict, dict):
        candidate = f"{nested_key}={quote(script_dict)}"
        if candidate.count("=") > 1:
            assert "'" not in candidate, """Keys cannot contain ` ` and `'` and `=` """
            candidate = f"'{candidate}'"
        return candidate + " "
    new_str = ""
    for k, v in script_dict.items():
        if k == "__value__":
            value = str(v)
            if " " in value:
                value = f"'{value}'"
            candidate = f"{nested_key}={quote(v)} "
            if candidate.count("=") > 1:
                assert (
                    "'" not in candidate
                ), """Keys cannot contain ` ` and `'` and `=` """
                candidate = f"'{candidate}'"
            new_str += candidate
            continue
        new_key = k if not nested_key else nested_key + "." + str(k)
        new_str += script_dict_to_script_args_str(v, nested_key=new_key, is_first=False)
    if is_first:
        new_str = new_str.strip()
    return new_str


def deep_update(a, b, path=None, verbose=None):
    """
    https://stackoverflow.com/questions/7204805/how-to-merge-dictionaries-of-dictionaries/7205107#7205107

    Args:
        a (dict): dict to update
        b (dict): dict to update from

    Returns:
        dict: updated copy of a
    """
    if path is None:
        path = []
        a = deepcopy(a)
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                deep_update(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                if verbose:
                    print(">>> Warning: Overwriting", ".".join(path + [str(key)]))
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a


def print_md_help(parser, defaults):
    global HELP

    print("# 🤝 Mila Launch tool help\n")
    print("## 💻 Command-line help\n")
    print("In the following, `$root` refers to the root of the current repository.\n")
    print("```sh")
    print(parser.format_help())
    print("```\n")
    print("## 🎛️ Default values\n")
    print(
        "```yaml\n"
        + "\n".join([f"{k}: {v}" for k, v in dict_to_print(defaults).items()])
        + "\n```"
    )
    print(HELP, end="")


def ssh_to_https(url):
    """
    Converts a ssh git url to https.
    Eg:
    """
    if "https://" in url:
        return url
    if "git@" in url:
        path = url.split(":")[1]
        return f"https://github.com/{path}"
    raise ValueError(f"Could not convert {url} to https")


def get_remotes_diff(repo, git_checkout):
    """
    Returns the number of commits behind and ahead of each remote for the given
    git checkout.

    Args:
        repo (git.Repo): git repo
        git_checkout (str): git checkout (branch or commit)

    Returns:
        dict, dict: behinds, aheads (as {"remote_name": int})
    """
    behinds = {}
    aheads = {}
    for r in repo.remotes:
        try:
            behinds[r.name] = len(
                list(repo.iter_commits(f"{git_checkout}..{r.name}/{git_checkout}"))
            )
        except GitCommandError as e:
            if "fatal: bad revision" in str(e):
                behinds[r.name] = f"checkout {git_checkout} found on remote {r.name}"
        try:
            aheads[r.name] = len(
                list(repo.iter_commits(f"{r.name}/{git_checkout}..{git_checkout}"))
            )
        except GitCommandError:
            # already caught and printed in commits behind
            pass

    return behinds, aheads


def validate_git_status(conf):
    """
    Validates the git status of the current repo.

    Args:
        conf (dict): Launch configuration

    Returns:
        Repo, str: git repo and git checkout
    """
    global GIT_WARNING
    get_user_input = False

    git_checkout = conf["git_checkout"]

    repo = Repo(ROOT)
    if not git_checkout:
        get_user_input = True
        git_checkout = repo.active_branch.name
        if GIT_WARNING:
            if not get_user_input:
                print("💥 Git warnings:")
            print(
                f"  • `--git_checkout` not provided. Using current branch: {git_checkout}"
            )
    # warn for uncommitted changes
    if repo.is_dirty() and GIT_WARNING:
        if not get_user_input:
            print("💥 Git warnings:")
        get_user_input = True
        print(
            "  • Your repo contains uncommitted changes. "
            + "They will *not* be available when cloning happens within the job."
        )
    behinds, aheads = get_remotes_diff(repo, git_checkout)
    if (any(behinds.values()) or any(aheads.values())) and GIT_WARNING:
        if not get_user_input:
            print("💥 Git warnings:")
        get_user_input = True
        for remote, b in behinds.items():
            if b:
                print(f"  • You are {b} commits behind {remote}/{git_checkout}")
        for remote, a in aheads.items():
            if a:
                print(f"  • You are {a} commits ahead of {remote}/{git_checkout}")

    if (
        GIT_WARNING
        and get_user_input
        and "y" not in input("Continue anyway? [y/N] ").lower()
    ):
        print("🛑 Aborted")
        sys.exit(0)

    GIT_WARNING = False  # only warn once per launch.py run (there may be multiple jobs)

    return repo, git_checkout


def code_dir_for_slurm_tmp_dir_checkout(conf):
    """
    Makes sure the code_dir is set to $SLURM_TMPDIR and that the git checkout
    is done there.

    Returns a multi-line formatted string that will be used for the `{code_dir}`
    template, i.e. will be prepended with `cd `.
    ```
    $SLURM_TMPDIR
    git clone {git_url} tmp-{repo_name}
    cd tmp-{repo_name}
    {git_checkout}
    echo "Current commit: $(git rev-parse HEAD)"
    ```

    Args:
        conf (dict): Launch configuration

    Returns:
        str: multi-line formatted string
    """

    repo, git_checkout = validate_git_status(conf)
    repo_url = repo.remotes.origin.url
    if conf["clone_as_https"]:
        repo_url = ssh_to_https(repo.remotes.origin.url)
    repo_name = repo.remotes.origin.url.split(".git")[0].split("/")[-1]

    return dedent(
        """\
        $SLURM_TMPDIR
        git clone {git_url} tmp-{repo_name}
        cd tmp-{repo_name}
        {git_checkout}
        echo "Current commit: $(git rev-parse HEAD)"
    """
    ).format(
        git_url=repo_url,
        git_checkout=f"git checkout {git_checkout}" if git_checkout else "",
        repo_name=repo_name,
    )


def load_launch_conf():
    """
    Loads the launch configuration file.
    """
    global GIT_WARNING

    launch_conf_path = ROOT / "config" / "templates" / "launch.conf.yaml"
    if not launch_conf_path.is_file():
        raise ValueError(
            f"Could not find launch configuration file at {launch_conf_path}"
        )
    with open(launch_conf_path, "r") as f:
        launch_conf = safe_load(f)

    GIT_WARNING = launch_conf.get("warn_no_checkout", True)

    return launch_conf


def parse_args_to_dict():
    """
    Parses the command-line arguments and returns a dict of args.
    """
    parser = ArgumentParser(add_help=False)
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        help="show this help message and exit",
        default=None,
    )
    parser.add_argument(
        "--help-md",
        action="store_true",
        help="Show an extended help message as markdown. Can be useful to overwrite "
        + "LAUNCH.md with `$ python mila/launch.py --help-md > LAUNCH.md`",
        default=None,
    )
    parser.add_argument(
        "--job_name",
        type=str,
        help="slurm job name to show in squeue."
        + f" Defaults to {launch_defaults['job_name']}",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        help="where to write the slurm .out file."
        + f" Defaults to {launch_defaults['outdir']}",
    )
    parser.add_argument(
        "--cpus_per_task",
        type=int,
        help="number of cpus per SLURM task."
        + f" Defaults to {launch_defaults['cpus_per_task']}",
    )
    parser.add_argument(
        "--mem",
        type=str,
        help="memory per node (e.g. 32G)." + f" Defaults to {launch_defaults['mem']}",
    )
    parser.add_argument(
        "--gres",
        type=str,
        help="gres per node (e.g. gpu:1)." + f" Defaults to {launch_defaults['gres']}",
    )
    parser.add_argument(
        "--partition",
        type=str,
        help="slurm partition to use for the job."
        + f" Defaults to {launch_defaults['partition']}",
    )
    parser.add_argument(
        "--time",
        type=str,
        help="wall clock time limit (e.g. 2-12:00:00). "
        + "See: https://slurm.schedmd.com/sbatch.html#OPT_time"
        + f" Defaults to {launch_defaults['time']}",
    )
    parser.add_argument(
        "--modules",
        type=str,
        help="string after 'module load'."
        + f" Defaults to {launch_defaults['modules']}",
    )
    parser.add_argument(
        "--conda_env",
        type=str,
        help="conda environment name." + f" Defaults to {launch_defaults['conda_env']}",
    )
    parser.add_argument(
        "--venv",
        type=str,
        help="path to venv (without bin/activate)."
        + f" Defaults to {launch_defaults['venv']}",
    )
    parser.add_argument(
        "--template",
        type=str,
        help="path to sbatch template." + f" Defaults to {launch_defaults['template']}",
    )
    parser.add_argument(
        "--code_dir",
        type=str,
        help="cd before running main.py."
        + f" Defaults to {launch_defaults['code_dir']}",
    )
    parser.add_argument(
        "--git_checkout",
        type=str,
        help="Branch or commit to checkout before running the code."
        + " This is only used if --code_dir='$SLURM_TMPDIR'. If not specified, "
        + " the current branch is used."
        + f" Defaults to {launch_defaults['git_checkout']}",
    )
    parser.add_argument(
        "--jobs",
        type=str,
        help="jobs (nested) file name in external/jobs (with or without .yaml)."
        + " Or an absolute path to a yaml file anywhere"
        + f" Defaults to {launch_defaults['jobs']}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't run just, show what it would have run."
        + f" Defaults to {launch_defaults['dry-run']}",
        default=None,
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print templated sbatch after running it."
        + f" Defaults to {launch_defaults['verbose']}",
        default=None,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip user confirmation." + f" Defaults to {launch_defaults['force']}",
        default=None,
    )
    parser.add_argument(
        "--command",
        type=str,
        help="Command to run." + f" Defaults to {launch_defaults['command']}",
    )

    parser.add_argument(
        "--script_path",
        type=str,
        help="Script to run by command."
        + f" Defaults to {launch_defaults['script_path']}",
    )

    parser.add_argument(
        "--sbatch_files_root",
        type=str,
        help="Where to write the sbatch files."
        + f" Defaults to {launch_defaults['sbatch_files_root']}",
    )
    parser.add_argument(
        "--prevent_unclean_repo",
        action="store_true",
        default=None,
        help="Raise an error if the git repo is not clean."
        + f" Defaults to {launch_defaults['prevent_unclean_repo']}",
    )
    parser.add_argument(
        "--warn_no_checkout",
        action="store_true",
        default=None,
        help="Warn if no git checkout is provided."
        + f" Defaults to {launch_defaults['warn_no_checkout']}",
    )
    parser.add_argument(
        "--clone_as_https",
        action="store_true",
        default=None,
        help="Clone the repo as https instead of ssh."
        + f" Defaults to {launch_defaults['clone_as_https']}",
    )

    known, unknown = parser.parse_known_args()

    cli_script_args = " ".join(unknown) if unknown else ""

    args = {k: v for k, v in vars(known).items() if v is not None}

    return args, cli_script_args, parser


def find_template(conf):
    """
    Finds the template file by considering it either a path to a file, or a file
    name in `config/templates/`.

    Args:
        conf (dict): Launch configuration

    Returns:
        Path: path to the template file
    """
    template_path = resolve(conf["template"])
    if not template_path.is_file():
        template_alternative = ROOT / "config" / "templates" / template_path.name
        if template_alternative.is_file():
            return template_alternative
        raise ValueError(
            f"Could not find template file at {template_path} or {template_alternative}"
        )
    return template_path


def dict_to_print(d):
    """
    Returns a dict with all the values as strings, and all the keys padded to
    the same length.

    Args:
        d (dict): dict to print

    Returns:
        dict: formatted dict
    """
    ml = max(len(k) for k in d) + 1
    keys = sorted(d.keys())
    return {f"{k:{ml}}": str(d[k]) if d[k] != "" else '""' for k in keys}


def load_template(conf):
    """
    Loads the template file.

    Args:
        conf (dict): Launch configuration

    Returns:
        dict: template as a string
    """
    template_path = find_template(conf)
    return template_path.read_text()


def clean_sbatch_params(templated):
    """
    Removes all SBATCH params that have an empty value.

    Args:
        templated (str): templated sbatch file

    Returns:
        str: cleaned sbatch file
    """
    new_lines = []
    for line in templated.splitlines():
        if not line.startswith("#SBATCH"):
            new_lines.append(line)
            continue
        if "=" not in line:
            new_lines.append(line)
            continue
        if line.split("=")[1].strip():
            new_lines.append(line)
    return "\n".join(new_lines)


if __name__ == "__main__":
    launch_defaults = load_launch_conf()

    args, cli_script_args, parser = parse_args_to_dict()

    if args.get("help_md"):
        print_md_help(parser, launch_defaults)
        sys.exit(0)
    if args.get("help"):
        print(parser.format_help())
        sys.exit(0)

    conf = deep_update(launch_defaults, args)
    print("🥁 Current Launch Configuration:")
    print("\n".join([f"  • {k}: {v}" for k, v in dict_to_print(conf).items()]))
    print()

    # load sbatch template file to format
    template = load_template(conf)
    # find the required formatting keys
    template_known_keys = set(re.findall(r"{(\w+)}", template))

    # in dry run mode: no mkdir, no sbatch etc.
    dry_run = conf["dry_run"]

    # in force mode, no confirmation is asked
    force = conf["force"]

    # where to write the slurm output file
    outdir = resolve(conf["outdir"])
    if not dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

    # find jobs config file in external/jobs as a yaml file
    jobs_conf_path, local_out_dir = find_jobs_conf(conf)
    # load yaml file as list of dicts. May be empty if jobs_conf_path is None
    job_dicts = load_jobs(jobs_conf_path)
    # No run passed in the CLI args or in the associated yaml file so run the
    # CLI script_args, if any.
    if not job_dicts:
        job_dicts = [{}]

    # Save submitted jobs ids
    job_ids = []
    job_out_files = []

    # A unique datetime identifier for the jobs about to be submitted
    now = now_str()

    if not force and not dry_run:
        if "y" not in input(f"🚨 Submit {len(job_dicts)} jobs? [y/N] ").lower():
            print("🛑 Aborted")
            sys.exit(0)
        print()

    for i, job_dict in enumerate(job_dicts):
        job_conf = conf.copy()
        job_conf = deep_update(job_conf, job_dict.pop("slurm", {}))
        job_conf = deep_update(job_conf, job_dict)
        job_conf = deep_update(job_conf, args)  # cli has the final say

        job_conf["code_dir"] = (
            str(resolve(job_conf["code_dir"]))
            if "SLURM_TMPDIR" not in job_conf["code_dir"]
            else code_dir_for_slurm_tmp_dir_checkout(job_conf)
        )
        job_conf["outdir"] = str(resolve(job_conf["outdir"]))
        job_conf["venv"] = str(resolve(job_conf["venv"]))
        job_conf["script_args"] = script_dict_to_script_args_str(
            job_conf.get("script", {})
        )
        if job_conf["script_args"] and cli_script_args:
            job_conf["script_args"] += " "
        job_conf["script_args"] += cli_script_args

        # filter out useless args for the template
        template_values = {
            k: str(v) for k, v in job_conf.items() if k in template_known_keys
        }
        # Make sure all the keys in the template are in the args
        if set(template_known_keys) != set(template_values.keys()):
            print(f"template keys: {template_known_keys}")
            print(f"template values: {template_values}")
            raise ValueError(
                "template keys != template args (see details printed above)"
            )

        # format template for this run
        templated = template.format(**template_values)
        templated = clean_sbatch_params(templated)  # remove empty #SBATCH params

        # set output path for the sbatch file to execute in order to submit the job
        if jobs_conf_path is not None:
            sbatch_path = local_out_dir / f"{jobs_conf_path.stem}_{now}_{i}.sbatch"
        else:
            sbatch_path = local_out_dir / f"{job_conf['job_name']}_{now}.sbatch"

        if not dry_run:
            # make sure the sbatch file parent directory exists
            sbatch_path.parent.mkdir(parents=True, exist_ok=True)
            # write template
            sbatch_path.write_text(templated)
            print()
            # Submit job to SLURM
            out = popen(f"sbatch {sbatch_path}").read().strip()
            # Identify printed-out job id
            job_id = re.findall(r"Submitted batch job (\d+)", out)[0]
            job_ids.append(job_id)
            print("  ✅ " + out)
            # Rename sbatch file with job id
            parts = sbatch_path.stem.split(f"_{now}")
            new_name = f"{parts[0]}_{job_id}_{now}"
            if len(parts) > 1:
                new_name += f"_{parts[1]}"
            sbatch_path = sbatch_path.rename(sbatch_path.parent / new_name)
            print(f"  🏷  Created ./{sbatch_path.relative_to(Path.cwd())}")
            # Write job ID & output file path in the sbatch file
            job_output_file = str(outdir / f"{job_conf['job_name']}-{job_id}.out")
            job_out_files.append(job_output_file)
            print("  📝  Job output file will be: " + job_output_file)
            templated += (
                "\n# SLURM_JOB_ID: "
                + job_id
                + "\n# Output file: "
                + job_output_file
                + "\n"
            )
            sbatch_path.write_text(templated)

        # final prints for dry_run & verbose mode
        if dry_run or conf.get("verbose"):
            if dry_run:
                print("\nDRY RUN: would have writen in sbatch file:", str(sbatch_path))
            print("#" * 40 + " <sbatch> " + "#" * 40)
            print(templated)
            print("#" * 40 + " </sbatch> " + "#" * 39)
            print()

    # Recap submitted jobs. Useful for scancel for instance.
    jobs_str = "⚠️ No job submitted!"
    if job_ids:
        jobs_str = "All jobs submitted: " + " ".join(job_ids)
        print(f"\n🚀 Submitted job {i+1}/{len(job_dicts)}")

    # make copy of original yaml conf and append all the sbatch info:
    if jobs_conf_path is not None:
        conf = jobs_conf_path.read_text()
        new_conf_path = local_out_dir / f"{jobs_conf_path.stem}_{now}.yaml"
        new_conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf += "\n# " + jobs_str + "\n"
        conf += (
            "\n# Job Output files:\n#"
            + "\n#".join([f"  • {f}" for f in job_out_files])
            + "\n"
        )
        rel = new_conf_path.relative_to(Path.cwd())
        if not dry_run:
            new_conf_path.write_text(conf)
            print(f"   Created summary YAML in {rel}")

    if job_ids:
        print(f"   {jobs_str}\n")
