from pathlib import Path

from invoke import Context, task


class Paths:
    repo_root = Path(__file__).parent
    example_tables = repo_root / "example_tables"


def from_repo_root(c: Context):
    return c.cd(Paths.repo_root)


@task
def compile_requirements(c: Context, install=True, upgrade=False):
    with from_repo_root(c):
        upgrade_flag = "--upgrade" if upgrade else ""
        c.run(f"pip-compile {upgrade_flag} -v --strip-extras --extra dev --extra build pyproject.toml", pty=True)
        c.run('echo "-e ." >> requirements.txt')
        if install:
            c.run("pip-sync", pty=True)


@task
def bumpver(c: Context, major=False, minor=False, patch=False, dry=False):
    num_set = 0
    flag = ""
    if major:
        flag = "--major"
        num_set += 1
    if minor:
        flag = "--minor"
        num_set += 1
    if patch:
        flag = "--patch"
        num_set += 1
    if num_set != 1:
        raise SystemExit("Must specify exactly one of --major, --minor, --patch")
    with from_repo_root(c):
        dry_flag = ""
        if dry:
            dry_flag = "--dry"
        c.run(f"bumpver update {flag} {dry_flag}", pty=True)


@task
def build(c: Context, clean=True):
    with from_repo_root(c):
        if clean:
            c.run("rm -rf dist/*")
        c.run("python -m build")
        c.run("twine check dist/*")


@task
def publish(c: Context, testpypi=True):
    if testpypi:
        testpypi_flag = "-r testpypi"
    else:
        testpypi_flag = ""
    with from_repo_root(c):
        c.run(f"twine upload {testpypi_flag} dist/*", pty=True)


@task
def lint(c: Context):
    with from_repo_root(c):
        c.run("black src/ tasks.py")
        c.run("isort src/ tasks.py")
        c.run("ruff src/ tasks.py --fix")


@task
def launch_dynamodb_local(c: Context, create_tables=False, clear_data=False):
    """Run local dynamodb, with options to wipe data and create a table with required indices."""
    with from_repo_root(c):
        c.run("docker stop dynamodb-local || true", hide="both")
        if clear_data:
            c.run("rm -rf $(pwd)/local/dynamodb")
        c.run(
            "docker run --rm -d --name dynamodb-local -p 8000:8000 -v "
            "$(pwd)/local/dynamodb:/data/ amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -dbPath /data"
        )
        if create_tables:
            for file in Paths.example_tables.iterdir():
                c.run(
                    f"AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=unused AWS_SECRET_ACCESS_KEY=unused "
                    f"aws dynamodb create-table --cli-input-yaml file://{file} --endpoint-url http://localhost:8000"
                )


@task
def halt_dynamodb_local(c: Context):
    """Run local dynamodb, with options to wipe data and create a table with required indices."""
    c.run("docker stop dynamodb-local || true", hide="both")


@task
def run_streamlit_app(c: Context):
    with from_repo_root(c):
        c.run("streamlit run ./streamlit_app.py --server.headless True")
