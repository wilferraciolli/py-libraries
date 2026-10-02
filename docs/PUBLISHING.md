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

### 2. Accounts and tokens (only on a computer you publish from)

TestPyPI and PyPI are **two separate sites with separate accounts and tokens**. A token from
one is rejected by the other.

| | TestPyPI (rehearsal) | PyPI (the real thing) |
|---|---|---|
| Register | <https://test.pypi.org/account/register/> | <https://pypi.org/account/register/> |
| Tokens page | <https://test.pypi.org/manage/account/token/> | <https://pypi.org/manage/account/token/> |
| Package page | <https://test.pypi.org/project/wiltech-labs-rest/> | <https://pypi.org/project/wiltech-labs-rest/> |
| `uv publish` flag | `--index testpypi` | *(none, it's the default)* |

On each site:

1. Register, confirm your email address, and turn on 2FA (both sites require it to upload).
2. **Account settings → API tokens → Add API token.** For the very first upload of a new
   package, set the scope to *Entire account* (the project doesn't exist yet). After the first
   release you can replace it with a token scoped to just that project.
3. Copy the token straight away; it's shown only once. It's one long line starting with `pypi-`.
   Keep it in a password manager, never in this repo.

Computers that only *use* the libraries need none of this. Downloading from PyPI is anonymous.

## Developing a package

From the repo root:

```bash
uv sync                                                   # one venv for the whole workspace
uv run --package wiltech-labs-rest pytest packages/rest   # tests for one package
```

## Releasing a new version

Every release follows the same steps. Run them from the package's folder, e.g. `packages/rest`.

### Step 1: test, bump, build

```bash
cd packages/rest

uv run pytest                      # tests must pass

uv version --bump patch            # patch = fix, minor = new feature, major = breaking change
                                   # (--dry-run to preview; skip this for the very first 0.1.0)
                                   # or set an exact version: uv version 1.0.0

rm -rf ../../dist                  # clear old builds so only this version is uploaded
uv build                           # writes the .whl and .tar.gz to the repo root's dist/
```

`uv publish --dry-run ../../dist/*` checks the files and the upload address without uploading.

### Step 2: rehearse on TestPyPI (optional, recommended)

```bash
# Prompt for the TestPyPI token without showing it or saving it in shell history
read -rsp "TestPyPI token: " UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN && echo

uv publish --index testpypi ../../dist/*

unset UV_PUBLISH_TOKEN             # don't leave the test token set for the real publish
```

`--index testpypi` is defined in the root `pyproject.toml` (it holds TestPyPI's upload URL).

Check it on <https://test.pypi.org/project/wiltech-labs-rest/>, then install it from there in a
throwaway environment:

```bash
uv run --no-project \
  --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match \
  --with wiltech-labs-rest \
  python -c "import wiltech_labs_rest as w; print(w.__all__)"
```

`--index-strategy unsafe-best-match` lets dependencies like `pydantic` come from the real PyPI,
because TestPyPI's copies of them are incomplete. If uv picks up an older cached copy, add
`--refresh`.

Publishing to TestPyPI doesn't use up the version number on the real PyPI, as they're
independent. A version *is* permanent within TestPyPI though, so to retry after a fix, bump the
version and rebuild.

### Step 3: publish to PyPI

```bash
read -rsp "PyPI token: " UV_PUBLISH_TOKEN && export UV_PUBLISH_TOKEN && echo

uv publish ../../dist/*

unset UV_PUBLISH_TOKEN
```

Check it on <https://pypi.org/project/wiltech-labs-rest/>. Once it's there, any app on any
computer can `uv add wiltech-labs-rest`.

PyPI's project page and JSON API can take a few minutes to show a new version (they're cached),
even though `uv` can already install it. If an app's `uv lock` says the new version doesn't
exist, run `uv lock --refresh` to bypass uv's own cached copy of the index.

> If you publish often from one computer, you can put `export UV_PUBLISH_TOKEN="pypi-..."` (the
> **PyPI** one) in `~/.bashrc` instead of typing it each time, and pass the TestPyPI token
> explicitly with `--token` when rehearsing.

### Step 4: commit and tag

So the source of every release can be found later:

```bash
git commit -am "wiltech-labs-rest 0.1.1"
git tag rest-v0.1.1
git push && git push --tags
```

### When publishing fails

| Error | Cause and fix |
|---|---|
| `403 Invalid or non-existent authentication information` | Wrong or missing token. Check that it comes from the **same site** you're publishing to (test.pypi.org vs pypi.org), that it was pasted whole including the `pypi-` start, and that the email is confirmed and 2FA is on. If unsure, create a new token. |
| `403 ... isn't allowed to upload to project` | The token is scoped to a different project, or the package name is taken by someone else. |
| `400 File already exists` | That version was already uploaded (even if later deleted). Bump the version, rebuild, and publish again. |
| Old version uploaded | `dist/` still had previous builds. `rm -rf ../../dist`, rebuild. |

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
