# Building, publishing and using the libraries

How the packages in this repo get from source to the FastAPI apps, on any computer.

## Where they're published: PyPI

The Python equivalent of npm is **PyPI** (<https://pypi.org>). It's where `uv add` / `pip install`
download packages from by default, so once a package is there, any app on any machine just lists
it as a dependency — no file paths, no git checkout of this repo.

| Angular (`ngx-libraries`) | Python (this repo) |
|---|---|
| npm registry — npmjs.com | PyPI — pypi.org |
| scope `@wiltech-labs/ngx-api-client` | name prefix `wiltech-labs-rest` (PyPI has no scopes) |
| `npm login` | a PyPI API token |
| `npm version patch` | `uv version --bump patch` |
| `npm run build` → `dist/` | `uv build` → `dist/` (wheel `.whl` + source `.tar.gz`) |
| `npm publish` | `uv publish` |
| `npm install @wiltech-labs/ngx-api-client` | `uv add wiltech-labs-rest` |

There is also **TestPyPI** (<https://test.pypi.org>), a separate sandbox registry for rehearsing a
release. It has its own account and tokens.

> **Versions are permanent.** Unlike npm's 72-hour unpublish, PyPI never lets you upload the same
> version number twice, even after deleting it. A broken release is fixed by publishing the next
> version (and optionally *yanking* the bad one on pypi.org, which hides it from new installs).

## One-time setup (per computer)

### 1. Install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # installs to ~/.local/bin
uv --version
```

> On the current Linux machine `uv` lives at `~/snap/code/current/.local/bin/uv` (installed from
> inside the VS Code snap), and `~/.profile` sources `~/snap/code/263/...`, a folder that no longer
> exists — so `uv` is missing from a normal terminal. Either install it as above, or change that
> `~/.profile` line to `. "$HOME/snap/code/current/.local/bin/env"`.

### 2. PyPI account and token (only on a computer you publish from)

1. Create an account at <https://pypi.org/account/register/> and enable 2FA (PyPI requires it to
   publish).
2. **Account settings → API tokens → Add API token.** For the very first upload of a new package
   the token must be scoped to *Entire account* (the project doesn't exist yet). After the first
   release, replace it with a token scoped to just that project.
3. Store it so `uv publish` picks it up — e.g. in `~/.bashrc` (never commit it):
   ```bash
   export UV_PUBLISH_TOKEN="pypi-AgEI..."
   ```
4. For rehearsals, repeat on <https://test.pypi.org> and keep that token separately — pass it with
   `--token` or swap `UV_PUBLISH_TOKEN` when publishing to TestPyPI.

Computers that only *use* the libraries need none of this — downloading from PyPI is anonymous.

## Developing a package

From the repo root:

```bash
uv sync                                                   # one venv for the whole workspace
uv run --package wiltech-labs-rest pytest packages/rest   # tests for one package
```

## Releasing a new version

Run from the package's folder, e.g. `packages/rest`:

```bash
cd packages/rest

# 1. Tests pass
uv run pytest

# 2. Bump the version in pyproject.toml (semver: patch = fix, minor = new feature, major = breaking)
uv version --bump patch            # or minor / major; --dry-run to preview

# 3. Build. Output goes to the workspace's dist/ (repo root); clear old builds first so
#    only this version gets uploaded.
rm -rf ../../dist
uv build

# 4. (optional) Rehearse on TestPyPI, then install it from there in a scratch venv
uv publish --index testpypi --token "$TEST_PYPI_TOKEN" ../../dist/*

# 5. Publish to PyPI
uv publish ../../dist/*
```

Then commit the version bump and tag it, so the source of every release can be found:

```bash
git commit -am "wiltech-labs-rest 0.1.1"
git tag rest-v0.1.1
git push && git push --tags
```

`uv publish --dry-run ../../dist/*` checks the files and the upload URL without uploading.

## Using a package in an app

In the FastAPI app (e.g. `fastapi-template`):

```bash
uv add wiltech-labs-rest            # adds it to pyproject.toml and uv.lock
```

```python
from wiltech_labs_rest import ApiResponse, FieldMetadata, Link, LinkedResource
```

Commit both `pyproject.toml` and `uv.lock`. On another computer, `uv sync` downloads the exact
locked version from PyPI.

Picking up a newer release:

```bash
uv lock --upgrade-package wiltech-labs-rest
uv sync
```

`uv add` writes a minimum version (`wiltech-labs-rest>=0.1.0`); `uv.lock` pins the exact one, so an
app only moves to a new release when you run the upgrade above.

### In Docker and on Cloudflare

- **Docker**: the image's `uv sync` downloads it from PyPI like every other dependency — nothing
  extra to do.
- **Cloudflare Python Workers**: `pywrangler` bundles the dependencies from `pyproject.toml`.
  The package is pure Python and only needs `pydantic`, which Workers support.

## Adding another package

See the "New package checklist" in the root `CLAUDE.md`. Each package is versioned, tagged
(`<folder>-v<version>`, e.g. `rest-v0.2.0`) and published on its own.
