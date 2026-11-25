"""Shared rules of the maxxfactory runtime. Every bin/ script imports this so that identity, exclusions,
config transactions, tree snapshots and verdict validation are enforced in exactly one place.

Config: $AUTOPILOT_CONFIG_DIR (default ~/.config/maxxfactory): models.json (roster, accounts, pools, health),
harnesses/ (adapter overrides), prompts/ (template overrides). Per project: <repo>/.maxxfactory/state.json (`.autopilot/` before 2026-11-23).
Python 3.9+ (no match statements, no nested same-quote f-strings).
"""
import contextlib, datetime as dt, fcntl, fnmatch, glob, hashlib, json, os, re, shutil, signal, subprocess, sys, tarfile, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
HOME = os.path.dirname(HERE)
_LEGACY_CONFIG_DIR = os.path.expanduser('~/.config/linear-autopilot')  # the project's former name
CONFIG_DIR = os.path.expanduser(os.environ.get('AUTOPILOT_CONFIG_DIR') or (
    _LEGACY_CONFIG_DIR if os.path.isdir(_LEGACY_CONFIG_DIR) and not os.path.exists(os.path.expanduser('~/.config/maxxfactory'))
    else '~/.config/maxxfactory'))
REG = os.path.join(CONFIG_DIR, 'models.json')
VERDICTS = ('approve', 'changes_required')
SEVERITIES = ('blocker', 'major', 'minor')
BLOCKING = ('blocker', 'major')
IMPACTS = ('fatal', 'severe', 'moderate')
FINDING_CLASSES = ('kpi-blocking', 'hardening', 'out-of-scope')  # only the first is folded into a plan; the others are parked as ideas
COSTS = ('high', 'mid', 'cheap', 'free')
# Project directory and ticket-branch prefix (2026-11-23: renamed from `.autopilot/` and `autopilot/`). Projects
# started before keep their `.autopilot/` until `bin/state migrate` moves it (never in the middle of a run), and
# ticket branches created before keep their `autopilot/<NAME>` name until they are merged and removed.
PROJECT_DIR, LEGACY_PROJECT_DIR = '.maxxfactory', '.autopilot'
BRANCH_PREFIX, LEGACY_BRANCH_PREFIXES = 'maxxfactory/', ('autopilot/',)
TICKET_BRANCH_PREFIXES = (BRANCH_PREFIX,) + LEGACY_BRANCH_PREFIXES
IGNORE_PREFIXES = (PROJECT_DIR + '/', LEGACY_PROJECT_DIR + '/', '.tmp/')


def now():
    return dt.datetime.now(dt.timezone.utc)


def parse_time(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))


# ---------- config transactions (one lock per file, unique temp files, atomic rename) ----------

@contextlib.contextmanager
def locked(path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path + '.lock', 'a+') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def read_json(path):
    with open(path) as f:
        return json.load(f)


def write_json_atomic(path, data):
    d = os.path.dirname(path) or '.'
    fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', dir=d)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


_WARNED = set()


def load_reg(warn=True):
    """The roster. Entries that break the tier policy (vendor -> CLI, level) are reported once per process on stderr;
    they stay in the file (so `bin/harness` can fix or remove them) but no pool ever selects them (see `refused`)."""
    if not os.path.exists(REG):
        sys.exit('no roster at %s. Run the maxxfactory-init skill (bin/harness init).' % REG)
    r = read_json(REG)
    if warn:
        try:
            bad = refused(r)
        except SystemExit:
            raise
        except Exception:
            bad = {}
        for k, why in sorted(bad.items()):
            if (k, why) not in _WARNED:
                _WARNED.add((k, why))
                print('roster: refused %s: %s' % (k, why), file=sys.stderr)
    return r


def update_reg(fn):
    """Locked read-modify-write of the roster. fn(r) mutates r and may return a value."""
    with locked(REG):
        r = load_reg(warn=False)
        out = fn(r)
        write_json_atomic(REG, r)
        return out


def pdir(repo, *parts):
    """The project's working directory `<repo>/.maxxfactory` (joined with `parts`). A project started before the rename
    keeps its `<repo>/.autopilot` (read and written in place) until `bin/state migrate` moves it."""
    new, old = os.path.join(repo, PROJECT_DIR), os.path.join(repo, LEGACY_PROJECT_DIR)
    if not os.path.exists(os.path.join(new, 'state.json')) and os.path.isdir(old) and not os.path.islink(old):
        return os.path.join(old, *parts)
    return os.path.join(new, *parts)


def ticket_branch(repo, name):
    """The branch of a ticket worktree: the `autopilot/<NAME>` branch an older version created when it exists (its work
    stays where it is), else `maxxfactory/<NAME>`."""
    for pre in LEGACY_BRANCH_PREFIXES:
        if git(repo, 'rev-parse', '-q', '--verify', 'refs/heads/' + pre + name).returncode == 0:
            return pre + name
    return BRANCH_PREFIX + name


def ensure_ignored(repo):
    """`.maxxfactory/` and the legacy `.autopilot` (directory or the link `bin/state migrate` leaves) in
    `.git/info/exclude`, so neither ever shows up as an untracked tree."""
    p = subprocess.run(['git', '-C', repo, 'rev-parse', '--git-common-dir'], capture_output=True, text=True)
    git_dir = (p.stdout or '').strip()
    if p.returncode != 0 or not git_dir:
        return
    excl = os.path.join(git_dir if os.path.isabs(git_dir) else os.path.join(repo, git_dir), 'info', 'exclude')
    os.makedirs(os.path.dirname(excl), exist_ok=True)
    prev = open(excl).read() if os.path.exists(excl) else ''
    lines = prev.splitlines()
    add = [x for x in (PROJECT_DIR + '/', LEGACY_PROJECT_DIR) if x not in lines]
    if add:
        open(excl, 'w').write(prev + ('\n' if prev and not prev.endswith('\n') else '') + ''.join(x + '\n' for x in add))


def migrate_project_dir(repo):
    """Moves a legacy `<repo>/.autopilot` to `<repo>/.maxxfactory` and leaves `.autopilot` as a link to it, so paths
    recorded before (briefs, logs, a coordinator's notes) still resolve. Refused while the pipeline lock is held or a
    background job runs: a run is never moved under its feet. Returns a one-line message."""
    new, old = os.path.join(repo, PROJECT_DIR), os.path.join(repo, LEGACY_PROJECT_DIR)
    if os.path.islink(old) or not os.path.isdir(old):
        ensure_ignored(repo)
        return 'nothing to migrate: %s is the project directory' % pdir(repo)
    if os.path.exists(new):
        raise SystemExit('state migrate: both %s and %s exist: merge them by hand, then rerun' % (old, new))
    if clock_alive(repo):
        raise SystemExit('state migrate: the pipeline runs: stop it first (pipeline stop), then rerun')
    busy = live_bg_jobs(repo)
    if busy:
        raise SystemExit('state migrate: background job(s) running: %s: wait for them, then rerun' % ', '.join(busy))
    os.rename(old, new)
    os.symlink(PROJECT_DIR, old)
    ensure_ignored(repo)
    return 'moved %s -> %s (%s left as a link)' % (old, new, LEGACY_PROJECT_DIR)


def state_path(repo):
    return pdir(repo, 'state.json')


def load_state(repo):
    p = state_path(repo)
    return read_json(p) if os.path.exists(p) else {}


def worktrees_dir(repo, st=None):
    """Where every worktree of a project is created: `<repo>-wt`, next to the repo. Derived from where the repo is
    now, never read from state.json: a recorded path survives a moved or renamed repo and then sends new worktrees to
    a place nobody excluded from Spotlight (seen 2026-11-22). `st` is accepted for older callers and ignored."""
    return os.path.abspath(repo).rstrip('/') + '-wt'


def legacy_worktrees_dir(repo, st=None):
    """A `worktrees_dir` an older version recorded in state.json, when it names another place than `<repo>-wt` (else
    None). Nothing is created there any more; the worktrees still in it finish there (each in-flight ticket records
    its own `wt`) and the garbage collection keeps collecting them."""
    st = load_state(repo) if st is None else st
    d = st.get('worktrees_dir')
    if not d or os.path.realpath(os.path.expanduser(d)) == os.path.realpath(worktrees_dir(repo)):
        return None
    return os.path.expanduser(d)


def in_worktrees_dir(repo, path, st=None):
    """True when path is inside the project's worktrees directory (or the legacy one of an older state.json)."""
    p = os.path.realpath(path) + '/'
    roots = [worktrees_dir(repo), legacy_worktrees_dir(repo, st)]
    return any(p.startswith(os.path.realpath(r).rstrip('/') + '/') for r in roots if r)


# ---------- Spotlight (macOS): agents rewrite thousands of files per hour; an indexed tree keeps mds busy ----------

def spotlight_count(d):
    """Items Spotlight has indexed under d: None when it cannot tell (not macOS, no mdfind, empty dir, error)."""
    mdfind = os.environ.get('AUTOPILOT_MDFIND') or shutil.which('mdfind')
    if not mdfind or not os.path.isdir(d) or not os.listdir(d):
        return None
    n = 0
    for q in (['kMDItemFSName == "*"'], ['-name', '.']):  # neither query alone sees every kind of item
        try:
            p = subprocess.run([mdfind, '-onlyin', d, '-count'] + q, capture_output=True, text=True, timeout=20,
                               stdin=subprocess.DEVNULL)
            n = max(n, int(p.stdout.strip().splitlines()[-1]))
        except (subprocess.SubprocessError, ValueError, IndexError, OSError):
            return None
    return n


def code_folder(repo):
    """The folder that holds the repo and, next to it, its `<repo>-wt` worktrees directory: the one folder to exclude
    from Spotlight. None when that folder is the home directory, a volume root or `/` (nobody excludes those)."""
    parent = os.path.dirname(os.path.realpath(repo).rstrip('/'))
    home = os.path.realpath(os.path.expanduser('~'))
    if (home + '/').startswith(parent.rstrip('/') + '/') or os.path.ismount(parent):
        return None
    return parent


def spotlight_dirs(repo):
    """The trees agents write to, as the folders to check: the folder that holds the repo and its `<repo>-wt`
    (code_folder), so a worktrees directory that does not exist yet, or was just emptied, is covered too. Without a
    usable parent folder: the repo and its worktrees directory themselves. Plus the worktrees directory of an older
    state.json while it still exists."""
    parent = code_folder(repo)
    dirs = [parent] if parent else [os.path.realpath(repo), os.path.realpath(worktrees_dir(repo))]
    legacy = legacy_worktrees_dir(repo)
    if legacy and not any((os.path.realpath(legacy) + '/').startswith(d.rstrip('/') + '/') for d in dirs):
        dirs.append(os.path.realpath(legacy))
    return [d for d in dict.fromkeys(dirs) if os.path.isdir(d)]


def spotlight_indexed(dirs):
    """[(dir, count)] for every dir Spotlight indexes."""
    return [(d, n) for d in dirs for n in [spotlight_count(d)] if n]


def update_state(repo, fn):
    """Locked read-modify-write of the project state. Coordinators use `bin/state` (same lock) for their own edits."""
    with locked(state_path(repo)):
        st = load_state(repo)
        out = fn(st)
        write_json_atomic(state_path(repo), st)
        return out


def find_repo(required=True, start=None):
    if os.environ.get('AUTOPILOT_REPO'):
        return os.environ['AUTOPILOT_REPO']
    d = os.path.abspath(start or os.getcwd())
    while d != '/':
        if os.path.exists(state_path(d)):
            return d
        d = os.path.dirname(d)
    if required:
        sys.exit('no .maxxfactory/state.json found above the current directory (set AUTOPILOT_REPO)')
    return None


# ---------- harness adapters, accounts, vendors, model identity ----------

def adapters():
    out = {}
    for d in (os.path.join(HOME, 'harnesses'), os.path.join(CONFIG_DIR, 'harnesses')):
        for p in sorted(glob.glob(os.path.join(d, '*.json'))):
            a = read_json(p); a['_path'] = p; out[a['name']] = a
    return out


def adapter_of(m, ad=None):
    a = (ad or adapters()).get(m['cli'])
    if not a:
        raise SystemExit("unknown harness '%s': add harnesses/%s.json (maxxfactory-init, bin/harness new)" % (m['cli'], m['cli']))
    return a


def effective_env(m, a):
    """The one environment a roster entry runs with, and that identity and path expansion use: the process
    environment without the account variable (a base entry is the default account), then the adapter's env, then the
    entry's account override (e.g. CODEX_HOME)."""
    env = dict(os.environ)
    if a.get('account_env') and a['account_env'] not in m.get('env', {}):
        # a base entry is the CLI's default account, whatever account the coordinator session itself runs on
        env.pop(a['account_env'], None)
    env.update({k: os.path.expanduser(str(v)) for k, v in a.get('run', {}).get('env', {}).items()})
    env.update({k: os.path.expanduser(str(v)) for k, v in m.get('env', {}).items()})
    return env


def expand_path(path, a, env):
    """~ and $VAR / ${VAR} against the effective env; the adapter's account_default only when the var is unset."""
    full = dict(env)
    k = a.get('account_env')
    if k and not full.get(k):
        full[k] = os.path.expanduser(a.get('account_default', ''))
    return os.path.expanduser(re.sub(r'\$\{?(\w+)\}?', lambda mt: full.get(mt.group(1), mt.group(0)), path))


def explicit_account(m, a):
    """The account a roster entry declares itself (its own env override), or None for the base entry."""
    k = a.get('account_env') if a else None
    return m.get('env', {}).get(k) if k else None


def account_of(m, a):
    """Account label as the CLI will see it: the declared override, else the inherited process env, else default."""
    k = a.get('account_env') if a else None
    if not k:
        return 'default'
    v = effective_env(m, a).get(k)
    default = os.path.expanduser(a.get('account_default', '')) if a.get('account_default') else ''
    if not v or (default and os.path.realpath(os.path.expanduser(v)) == os.path.realpath(default)):
        return 'default'
    return '%s=%s' % (k, v)


def account_homes(a, reg=None):
    """Every account of a harness present on this machine, as (label, home): the default home as `<cli>`, the standard
    `<default>-<letter>` homes as `<cli>-<letter>`, and any non-standard home the roster declares as `<cli>@<home>`.
    A harness without account_env has one account, label `<cli>`, home None. Only existing directories count."""
    cli = a['name']
    k = a.get('account_env')
    if not k:
        return [(cli, None)]
    default = os.path.expanduser(a.get('account_default', '')).rstrip('/')
    out, seen = [], set()
    if default and os.path.isdir(default):
        out.append((cli, default)); seen.add(os.path.realpath(default))
    for p in sorted(glob.glob(os.path.expanduser(a.get('account_detect') or (default + '-[a-z]')))):
        if os.path.isdir(p) and os.path.realpath(p) not in seen:
            out.append(('%s-%s' % (cli, os.path.basename(p).rsplit('-', 1)[-1]), p.rstrip('/'))); seen.add(os.path.realpath(p))
    for m in (reg or {}).get('models', {}).values():
        if m.get('cli') != cli:
            continue
        home = explicit_account(m, a)
        if home and os.path.isdir(os.path.expanduser(home)) and os.path.realpath(os.path.expanduser(home)) not in seen:
            out.append(('%s@%s' % (cli, home.replace(os.path.expanduser('~'), '~')), os.path.expanduser(home).rstrip('/'))); seen.add(os.path.realpath(os.path.expanduser(home)))
    return out


VENDOR_HINTS = [('claude', 'anthropic'), ('gpt', 'openai'), ('codex', 'openai'), (r'\bo\d-', 'openai'), ('gemini', 'google'),
                ('grok', 'xai'), ('deepseek', 'deepseek'), ('glm', 'zhipu'), ('mistral', 'mistral'), ('devstral', 'mistral'),
                ('qwen', 'alibaba'), ('kimi', 'moonshot'), ('llama', 'meta'), ('nemotron', 'nvidia'), ('mimo', 'xiaomi'), ('beam', 'opencode')]


def vendor_of(m, a=None):
    if m.get('vendor'):
        return m['vendor']
    a = a or adapter_of(m)
    if a.get('vendor') and a['vendor'] != 'by_model':
        return a['vendor']
    mid = m['model'].lower()
    for hint, v in VENDOR_HINTS:
        if re.search(hint, mid):
            return v
    return m['cli']


def canonical_id(model):
    """The underlying model, whatever harness exposes it: provider prefixes (`opencode/`, `openrouter/anthropic/`),
    variant suffixes (`:free`, `#max`, `-thinking`, `-high`) and separators are stripped. A roster entry may
    pin its own `canonical` when the heuristic is wrong."""
    s = str(model).lower().split('/')[-1]
    s = re.sub(r'[#:].*$', '', s)
    for _ in range(3):  # peel stacked suffixes: `-flash-free`, `-thinking-high`, ...
        s = re.sub(r'-(thinking|high|medium|low|max|latest|preview|free|beta)$', '', s)
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def model_identity(m):
    return m.get('canonical') or canonical_id(m['model'])


def healthy(r, key):
    h = r['health'].get(key)
    return not h or parse_time(h['until']) < now()


def cool(key, reason, minutes=None, windows=None):
    """windows: the quota windows responsible (e.g. ['5h', 'weekly']); a cooldown is cleared by `usage --apply` only
    when a newer below-quota reading covers every one of them."""
    def fn(r):
        m = minutes or r.get('cooldown_minutes', 30)
        r['health'][key] = {'until': (now() + dt.timedelta(minutes=m)).isoformat(), 'reason': reason[:200], 'set_at': now().isoformat(),
                            'windows': sorted(windows) if windows else None}
    update_reg(fn)


def record_ok(key):
    """A successful run or smoke of `key`: proof that its quota windows were open at this time. `run-model usage
    --apply` treats any reading observed before it as stale (see last_ok)."""
    update_reg(lambda r: r.setdefault('last_ok', {}).__setitem__(key, now().isoformat()))


def last_ok(r, keys):
    """Latest successful run or smoke among `keys`, as a datetime, or None."""
    ts = [parse_time(r.get('last_ok', {})[k]) for k in keys if k in r.get('last_ok', {})]
    return max(ts) if ts else None


# ---------- critical alerts (the coordinator must tell the owner; see bin/alert) ----------
# One JSON object per line: id, level, kind (vendor_out | pool_blocked), key (vendor or pool), at, message, details,
# acked_at, resolved_at. Written to <repo>/.maxxfactory/alerts.jsonl, or to $AUTOPILOT_CONFIG_DIR/alerts.jsonl when the
# writer runs outside a project. An alert stays listed until it is acknowledged, even once resolved, so an outage that
# ended while the owner was away is still reported.

def alerts_path(repo):
    return pdir(repo, 'alerts.jsonl') if repo else os.path.join(CONFIG_DIR, 'alerts.jsonl')


def read_alerts(path):
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []


def update_alerts(repo, fn):
    """Locked read-modify-write of one alerts file. fn(alerts) mutates the list and may return a value."""
    path = alerts_path(repo)
    with locked(path):
        al = read_alerts(path)
        out = fn(al)
        d = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(prefix='.alerts.', dir=d)
        with os.fdopen(fd, 'w') as f:
            f.write(''.join(json.dumps(a) + '\n' for a in al))
        os.replace(tmp, path)
        return out


def alerts(repo, include_acked=False):
    """Alerts of the project and the machine-level ones (written outside a project), unacknowledged unless asked."""
    paths = list(dict.fromkeys([alerts_path(repo), alerts_path(None)]))
    return [dict(a, _file=p) for p in paths for a in read_alerts(p) if include_acked or not a.get('acked_at')]


def alert_line(a):
    state = 'resolved %s' % a['resolved_at'][:16] if a.get('resolved_at') else 'ACTIVE'
    return '%s: [%s] %s (since %s, %s)' % (a.get('level', 'CRITICAL'), a['id'], a['message'], a['at'][:16], state)


def issue_from_brief(path):
    mt = re.match(r'(.+?)-(impl|review|plan|diag)-', os.path.basename(path))
    return mt.group(1) if mt else None


def expand_exclusions(reg, keys=(), vendors=(), identities=(), ad=None):
    """Every roster key that must not be used: the keys given, every key whose underlying model is the same as any
    of them or of `identities` (another account, another harness, an upgraded or removed key), and every key of
    the vendors given."""
    ad = ad or adapters()
    ex = set(k for k in keys if k)
    ids = set(i for i in identities if i) | {model_identity(reg['models'][k]) for k in ex if k in reg['models']}
    for k, m in reg['models'].items():
        if model_identity(m) in ids or (vendors and vendor_of(m, ad.get(m['cli'])) in vendors):
            ex.add(k)
    return ex


def review_exemptions(repo, reg):
    """Roster keys an owner exception lets review a ticket their model implemented. state.json
    `review_same_model` = {"identities": [<model identity>], "until": <ISO time>, "source": <owner words>}; past
    `until` it is ignored. The owner grants it for a quota gap (no other reviewer left); the default is none."""
    o = (load_state(repo) if repo else {}).get('review_same_model') or {}
    try:
        if not o.get('until') or now() >= dt.datetime.fromisoformat(o["until"]):
            return set()
    except ValueError:
        return set()
    ids = set(o.get('identities') or [])
    return {k for k, m in reg['models'].items() if model_identity(m) in ids}


def implementers_of(repo, issue):
    """(roster keys, model identities) recorded for a ticket. Identities survive roster edits."""
    st = load_state(repo) if repo else {}
    if not issue:
        return [], []
    return list(st.get('implementers', {}).get(issue, [])), list(st.get('implementer_ids', {}).get(issue, []))


def record_implementer(repo, issue, key, m, a):
    def fn(st):
        keys = st.setdefault('implementers', {}).setdefault(issue, [])
        if key not in keys:
            keys.append(key)
        ids = st.setdefault('implementer_ids', {}).setdefault(issue, [])
        ident = model_identity(m)
        if ident not in ids:
            ids.append(ident)
        st.setdefault('implementer_log', {}).setdefault(issue, []).append(
            {'key': key, 'model': m['model'], 'identity': ident, 'account': account_of(m, a), 'at': now().isoformat()})
    update_state(repo, fn)


# ---------- working tree snapshots (reviewers must not change the tree; some do) ----------

def git(cwd, *a):
    return subprocess.run(['git', '-C', cwd, *a], capture_output=True, text=True)


STACK_SUBJECT = 'maxxfactory-stack '  # subject of the snapshot commit a stacked ticket starts on (bin/pipeline "Stacked starts")


def stack_commit(wt, branch):
    """The sha of the stack commit of a worktree (the newest commit of `branch..HEAD` whose subject starts with
    STACK_SUBJECT), or None. A ticket started on its unmerged blocker carries that blocker's work as this one commit:
    it is the base of the ticket's own diff (review, changed files) and is dropped when the blocker is merged."""
    out = git(wt, 'log', '--format=%H%x09%s', '%s..HEAD' % branch).stdout
    for line in out.splitlines():
        sha, _, subj = line.partition('\t')
        if subj.startswith(STACK_SUBJECT):
            return sha
    return None


def is_git(cwd):
    return git(cwd, 'rev-parse', '--git-dir').returncode == 0


def untracked(cwd):
    return [f for f in git(cwd, 'ls-files', '-o', '--exclude-standard', '-z').stdout.split('\0') if f]


def head_state(cwd):
    return git(cwd, 'rev-parse', 'HEAD').stdout.strip() + ' ' + git(cwd, 'rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()


def tracked_state(cwd):
    """Status + unstaged and staged diffs with full binary patches, so a rewritten binary changes it too."""
    return (git(cwd, 'status', '--porcelain').stdout + git(cwd, 'diff', '--binary').stdout + git(cwd, 'diff', '--cached', '--binary').stdout)


def file_digest(path, limit=64 * 1024 * 1024):
    h = hashlib.sha1()
    try:
        st = os.stat(path)
        if st.st_size > limit:
            return 'big:%d:%d' % (st.st_size, st.st_mtime_ns)
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return 'missing'


def untracked_digest(cwd, ignore_prefixes=IGNORE_PREFIXES):
    return {f: file_digest(os.path.join(cwd, f)) for f in sorted(untracked(cwd)) if not f.startswith(ignore_prefixes)}


def tree_fingerprint(cwd, ignore_prefixes=IGNORE_PREFIXES):
    """HEAD + branch + tracked state (binary-safe) + content digest of every untracked file. None outside git."""
    if not is_git(cwd):
        return None
    h = hashlib.sha1()
    h.update(head_state(cwd).encode())
    h.update(tracked_state(cwd).encode(errors='ignore'))
    for f, d in untracked_digest(cwd, ignore_prefixes).items():
        h.update(('%s\0%s\n' % (f, d)).encode(errors='ignore'))
    return h.hexdigest()


def snapshot(cwd, ignore_prefixes=IGNORE_PREFIXES):
    """Tracked changes as a stash commit (does not touch files), staged state, untracked files in a tar, HEAD."""
    if not is_git(cwd):
        return None
    d = tempfile.mkdtemp(prefix='autopilot-snap-')
    snap = {'stash': git(cwd, 'stash', 'create').stdout.strip() or None, 'tar': os.path.join(d, 'untracked.tar'),
            'cached': git(cwd, 'diff', '--cached', '--binary').stdout, 'ignore': ignore_prefixes, 'head': head_state(cwd)}
    files = [f for f in untracked(cwd) if not f.startswith(ignore_prefixes)]
    with tarfile.open(snap['tar'], 'w') as tf:
        for f in files:
            try:
                tf.add(os.path.join(cwd, f), arcname=f)
            except FileNotFoundError:
                pass
    snap['untracked'] = untracked_digest(cwd, ignore_prefixes)
    snap['tracked'] = tracked_state(cwd)
    snap['fp'] = tree_fingerprint(cwd, ignore_prefixes)
    return snap


def restore(cwd, snap, junk_label='reviewer-junk'):
    """'unchanged', 'restored', 'history_changed' (HEAD or branch moved: never rewritten automatically, the caller
    stops) or 'restore_failed'. New untracked files are moved to .tmp/<junk_label>/."""
    if not snap:
        return 'unchanged'
    if tree_fingerprint(cwd, snap['ignore']) == snap['fp']:
        return 'unchanged'
    if head_state(cwd) != snap['head']:
        return 'history_changed'
    git(cwd, 'reset', '-q')
    git(cwd, 'checkout', '--', '.')
    if snap['stash']:
        git(cwd, 'stash', 'apply', '-q', snap['stash'])
    if snap['cached']:
        subprocess.run(['git', '-C', cwd, 'apply', '--cached', '--allow-empty'], input=snap['cached'], text=True, capture_output=True)
    junk = os.path.join(cwd, '.tmp', junk_label)
    for f in untracked(cwd):
        if f.startswith(snap['ignore']) or f in snap['untracked']:
            continue
        dst = os.path.join(junk, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.replace(os.path.join(cwd, f), dst)
        except FileNotFoundError:
            pass
    with tarfile.open(snap['tar']) as tf:
        tf.extractall(cwd)
    ok = tracked_state(cwd) == snap['tracked'] and untracked_digest(cwd, snap['ignore']) == snap['untracked']
    return 'restored' if ok else 'restore_failed'


# ---------- verdicts ----------

def digest_text(text):
    return hashlib.sha1(text.encode(errors='ignore')).hexdigest()


def parse_json_block(path):
    t = open(path, errors='ignore').read() if os.path.exists(path) else ''
    blocks = re.findall(r'```json\s*(\{.*?\})\s*```', t, re.S) or re.findall(r'(\{\s*"verdict".*\})', t, re.S)
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except Exception:
            pass
    return None


def validate_verdict(v):
    """(status, blocking lines). status: 'approve', 'changes', or 'invalid'. Fails closed: an approve with a
    blocking finding or an unmet criterion is 'changes'; an unknown verdict or malformed findings is 'invalid'."""
    if not isinstance(v, dict) or v.get('verdict') not in VERDICTS:
        return 'invalid', ['verdict missing or not in %s: %s' % (VERDICTS, str(v)[:120])]
    findings = v.get('findings', [])
    unmet = v.get('unmet_criteria', [])
    if not isinstance(findings, list) or not isinstance(unmet, list) or any(not isinstance(f, dict) for f in findings):
        return 'invalid', ['findings/unmet_criteria malformed']
    bl = []
    for f in findings:
        sev = f.get('severity')
        if sev not in SEVERITIES:
            return 'invalid', ['finding with unknown severity %r' % sev]
        if sev in BLOCKING:
            bl.append('[%s] %s:%s %s -> %s' % (sev, f.get('file'), f.get('line'), str(f.get('problem', ''))[:300], str(f.get('fix', ''))[:200]))
    bl += ['[unmet] ' + str(u)[:300] for u in unmet]
    if v['verdict'] == 'approve' and not bl:
        return 'approve', []
    if v['verdict'] == 'changes_required' and not bl:
        return 'changes', ['[changes_required] reviewer asked for changes without a blocking finding: ' + str(v.get('summary', ''))[:300]]
    return 'changes', bl


def validate_reasons(j):
    """Pre-mortem output -> (valid reasons, dropped count). A reason needs an id or title, an allowed impact and a
    numeric probability in [0, 1]; anything else is dropped (reported, never merged). There is no expected number of
    reasons (2026-11-25: the prompts asked for "at most 10" and every list came back with exactly 10). `class`
    (FINDING_CLASSES) defaults to kpi-blocking."""
    if not isinstance(j, dict) or j.get('verdict') != 'premortem' or not isinstance(j.get('reasons'), list):
        return None, 0
    good, dropped = [], 0
    for r in j['reasons']:
        try:
            if not isinstance(r, dict):
                raise ValueError
            p = float(r.get('probability'))
            text_ok = all(isinstance(r.get(f), str) and r.get(f).strip() for f in ('why', 'guardrail'))
            if not (r.get('id') or r.get('title')) or r.get('impact') not in IMPACTS or not (0.0 <= p <= 1.0) or not text_ok:
                raise ValueError
        except (TypeError, ValueError, AttributeError):
            dropped += 1
            continue
        r = dict(r); r['probability'] = p
        if r.get('class') not in FINDING_CLASSES:
            r['class'] = 'kpi-blocking'  # an untagged reason is never parked silently
        r['id'] = str(r.get('id') or re.sub(r'[^a-z0-9]+', '-', str(r['title']).lower())[:40])
        r['title'] = str(r.get('title') or r['id'])
        for f in ('why', 'early_signal', 'guardrail', 'kpi_link', 'source'):
            v = r.get(f)
            r[f] = v if isinstance(v, str) else ('' if v is None else str(v))
        good.append(r)
    return good, dropped


# ---------- tier policy (README "Tiers") ----------
# Every roster entry has a `level` (0-4) and a `vendor`. Pools are not hand-ordered lists any more: each role allows
# some levels (models.json `roles`, bounded by ROLES_ALLOWED) and `pool()` builds the candidates from the roster.
#   Tier 0 frontier: the planning phase (2026-11-25): the planner session of /maxxfactory-plan and plan-more, and the
#          plan roles (pre-mortem, plan review, milestone review), drawn before Tier 1. When no Tier 0 model of another
#          vendor than the planner is eligible and healthy, a plan role takes a Tier 1 model instead of waiting, logged
#          (run-model, state.json `tier_fallbacks`). models.json `"plan_tier0": false` keeps the plan roles on Tier 1.
#          Any other role: never automatic (owner opt-in per run: run-model --allow-tier0 --model KEY).
#   Tier 1 flagship: coordination of a run; the plan roles when no Tier 0 is eligible; the Express lane (2026-11-25):
#          `express_implement` writes a small change in one worktree and `express_review` reviews its final diff (two
#          reviewers of two vendors, in parallel). Outside Express it never implements, and reviews a ticket's code
#          only as the logged backup when no Tier 2 reviewer is eligible and healthy (REVIEW_FALLBACK).
#   Tier 2 balanced: ticket code reviews (two reviewers of distinct vendors); `escalate` implements rounds past
#          `escalate_after_round` (run-model run_role, default 3).
#   Tier 3 fast and cheap: ticket implementation and fix rounds up to `escalate_after_round`.
#   Tier 4 small: every Mistral model, every free model, old Gemini, whatever the tier table says. Trivial tasks only,
#          never a reviewer.
# Vendor -> CLI is fixed: a model is only ever reached through its vendor's own CLI (VENDOR_CLIS); any other vendor
# goes through opencode (OpenCode Go or OpenRouter). An entry that breaks it is refused, not repaired.

VENDOR_CLIS = {'anthropic': ('claude',), 'openai': ('codex',), 'google': ('agy',), 'mistral': ('vibe',), 'xai': ('grok',)}
OTHER_VENDOR_CLIS = ('opencode', 'pi')
LEVELS = (0, 1, 2, 3, 4)
ROLES_DEFAULT = {'implement': [2], 'fix': [2], 'review': [2], 'plan_review': [0, 1], 'premortem': [0, 1],
                 'milestone_review': [0, 1], 'coordinate': [1], 'trivial': [4], 'express_implement': [1], 'express_review': [1]}
ROLES_ALLOWED = {'implement': {2, 3}, 'fix': {2, 3}, 'review': {2}, 'plan_review': {0, 1}, 'premortem': {0, 1},
                 'milestone_review': {0, 1}, 'coordinate': {1}, 'trivial': {3, 4}, 'express_implement': {1}, 'express_review': {1}}
PLAN_ROLES = ('plan_review', 'premortem', 'milestone_review')  # review the planner's work: the planner's vendor is excluded
EXPRESS_ROLES = ('express_implement', 'express_review')         # the Express lane: Tier 1 writes, two Tier 1 vendors review
REVIEW_ROLES = ('review', 'express_review') + PLAN_ROLES        # roles a `run-model run review` may take
CHEAP_ROLES = ('implement', 'fix', 'trivial')                    # the coordinator's own account may take these, last
# Policy: after escalation every Tier 2 model may have implemented a ticket. When no Tier 2
# reviewer is eligible and healthy (or every one failed), bin/review draws the ticket reviewer from this role's tier
# (Tier 1) instead of waiting: credit-weighted, never the coordinator's own account, never an implementer's model,
# never an excluded or reserved account; logged in state.json `review_fallbacks` and on stderr. Plan roles have none.
REVIEW_FALLBACK = {'review': 'express_review'}  # a Tier 1 role (the plan roles now start at Tier 0, which never reviews ticket code)
# Legacy pool names (before 2026-11-09) and the role they now mean. `escalate` = one level above implement, never Tier 1.
POOL_ROLE = {'implement': 'implement', 'implement_critical': 'implement', 'fix': 'fix', 'fix_mid': 'fix',
             'implement_escalation': 'escalate', 'escalate': 'escalate', 'review': 'review', 'review_mid': 'review',
             'review_high': 'review', 'plan_review': 'plan_review', 'premortem': 'premortem',
             'milestone_review': 'milestone_review', 'coordinate': 'coordinate', 'trivial': 'trivial',
             'express_implement': 'express_implement', 'express_review': 'express_review'}
# subscription (gathered by /maxxfactory-init, never a default): paid (a plan the owner pays for), paid? (paid, plan not
# confirmed), free (free plan, low limits), reserved (the owner keeps it for other uses: never selected). `excluded:
# "<reason>"` on an entry, or a project's state.json `exclude` ({"<key>|<cli>/<account>|<cli>": "<reason>"}), removes
# entries too. The coordinator's own account is not a subscription: it is detected at run time (`coordinator_account`).
SUBSCRIPTIONS = ('paid', 'paid?', 'free', 'reserved')
SUB_RANK = {'paid': 0, 'paid?': 1, 'free': 2}
FREE_ID = re.compile(r'(?:[-:/]free)(?:#.*)?$|^openrouter/openrouter/free', re.I)
# The owner's tier table (Nov 2026), first match wins, matched on the model id. models.json `tier_table` entries come
# first. It assigns a level to a new entry and re-levels an upgraded id; Tier 4 overrides (Mistral, free) are in code.
# Speed variants have no row: they are refused (FAST_ID).
DEFAULT_TIER_TABLE = [
    {'match': r'mythos|fable', 'level': 0}, {'match': r'gpt-[\d.]+-astra', 'level': 0}, {'match': r'gemini-[\d.]+-carbon', 'level': 0},
    {'match': r'claude-opus', 'level': 1}, {'match': r'gpt-[\d.]+-sol', 'level': 1}, {'match': r'gemini-[\d.]+-argon', 'level': 1},
    {'match': r'muse-spark', 'level': 1}, {'match': r'kimi-k\d', 'level': 1},
    {'match': r'qwen[\d.]+-max', 'level': 1}, {'match': r'deepseek-v[\d.]+-pro', 'level': 1},
    {'match': r'claude-sonnet', 'level': 2}, {'match': r'mistral-large-[\d-]+', 'level': 2, 'why': 'Mistral Large 4 ("Le Chonk") on Vibe: the one Mistral model above Tier 4'}, {'match': r'gpt-[\d.]+-terra', 'level': 2}, {'match': r'gemini-3\.8-flash(?!-lite)', 'level': 2}, {'match': r'gemini-[\d.]+-hydrogen', 'level': 2},
    {'match': r'grok-4\.7', 'level': 2}, {'match': r'grok-4\.3', 'level': 2}, {'match': r'qwen[\d.]+-plus', 'level': 2},
    {'match': r'opencode-go/deepseek-v[\d.]+-flash', 'level': 2, 'why': 'OpenCode Go DeepSeek Flash is Tier 2; the free id stays Tier 4'},
    {'match': r'zai-coding-plan/glm-5\.4(?![\d-])', 'level': 2, 'why': 'GLM 5.4 on a Z.ai coding plan (through opencode) is the Tier 2 GLM of that plan, in place of GLM 5.3 Flash: the plan gives it about 50% more usage (2026-11-22)'},
    {'match': r'deepseek-v[\d.]+-flash|glm-[\d.]+-flash|qwen[\d.]+-flash', 'level': 2, 'why': 'the Max, Pro and plain GLM models are Tier 1, their Flash models Tier 2 (free ids stay Tier 4)'},
    {'match': r'claude-haiku', 'level': 3}, {'match': r'gpt-[\d.]+-luna', 'level': 3}, {'match': r'gemini-[\d.]+-flash-lite', 'level': 3},
    {'match': r'glm-[\d.]+', 'level': 1},
    {'match': r'gemini-(?:[0-2]\.|3\.[0-4](?!\d))', 'level': 4, 'why': 'old Gemini'},
]


# Policy: never a speed variant of a model family ('-fast', 'build-fast', 'Fast', e.g.
# grok-4.7-build-fast), whatever its tier: it costs more for the same answers. Such an entry is refused (entry_problems:
# no pool, no --model), `harness add-model`/`init` and `run-model discover` do not add one, unless the owner passes
# --allow-fast (stored as `allow_fast: true` on the entry). "Flash" / "Flash-Lite" (Gemini, DeepSeek, GLM) are model
# families, not speed variants: allowed.
FAST_ID = re.compile(r'(?<![a-z0-9])fast(?![a-z0-9])', re.I)
FAST_WHY = 'speed variant (-fast): more expensive, no quality gain (policy); only with the owner\'s explicit --allow-fast'


def is_fast_model(model_id):
    return bool(FAST_ID.search(str(model_id)))


def is_free_model(m):
    return m.get('cost') == 'free' or bool(FREE_ID.search(str(m.get('model', ''))))


def hinted_vendor(model_id):
    """The vendor the model id names (provider prefixes included: `openrouter/anthropic/...`), or None."""
    mid = str(model_id).lower()
    for hint, v in VENDOR_HINTS:
        if re.search(hint, mid):
            return v
    return None


def tier_table(r):
    return list((r or {}).get('tier_table') or []) + DEFAULT_TIER_TABLE


def table_level(r, model_id):
    """(level, entry) from the tier table for a model id, or (None, None)."""
    for e in tier_table(r):
        if re.search(e['match'], str(model_id), re.I):
            return int(e['level']), e
    return None, None


MISTRAL_ABOVE_FOUR = re.compile(r'mistral-large', re.I)  # Mistral Large 4 is Tier 2; every other Mistral model Tier 4


def forced_four(m, a=None):
    """Why the owner's rule puts this entry at Tier 4 whatever its level says, or None.

    `owner_tier` on a roster entry is the owner's explicit, sourced exception (e.g. a free model the owner allows as a
    Tier 2 reviewer): the entry then keeps its `level`. Set it only with the owner's words as its value.
    """
    if m.get('owner_tier'):
        return None
    if vendor_of(m, a) == 'mistral' and not MISTRAL_ABOVE_FOUR.search(str(m.get('model', ''))):
        return 'Mistral model'
    if is_free_model(m):
        return 'free model'
    return None


def level_of(r, m, a=None):
    """The level the policy uses: Tier 4 when forced, else the entry's `level`, else the tier table. None = unknown."""
    if forced_four(m, a):
        return 4
    if m.get('level') is not None:
        return int(m['level'])
    return table_level(r, m.get('model', ''))[0]


def entry_problems(r, key, m, ad=None):
    """Why the policy refuses a roster entry ([] = valid): unknown harness, a vendor reached through another vendor's
    CLI, a declared vendor that contradicts the model id, a speed variant without `allow_fast`, no level, an unknown
    subscription."""
    ad = ad if ad is not None else adapters()
    a = ad.get(m.get('cli'))
    if not a:
        return ["unknown harness '%s'" % m.get('cli')]
    out = []
    v = vendor_of(m, a)
    hv = hinted_vendor(m.get('model', ''))
    if hv in VENDOR_CLIS and v != hv:
        out.append('model id %s names vendor %s but the entry says %s' % (m.get('model'), hv, v))
    for vv in {v, hv} - {None}:
        clis = VENDOR_CLIS.get(vv, OTHER_VENDOR_CLIS)
        # Owner exception, per entry: `cross_cli_ok` holds the owner's words allowing this vendor through this CLI
        # (2026-11-19: Claude and GPT models through agy, whose quota is separate from the vendors' own plans).
        if m['cli'] not in clis and not m.get('cross_cli_ok'):
            out.append('%s models run only through %s, not %s' % (vv, ' or '.join(clis), m['cli']))
    if is_fast_model(m.get('model', '')) and not m.get('allow_fast'):
        out.append('%s is a %s' % (m.get('model'), FAST_WHY))
    lv = level_of(r, m, a)
    if lv is None:
        out.append('no level (set `level` 0-4, or add the family to the tier table)')
    elif lv not in LEVELS:
        out.append('level %r not in 0-4' % lv)
    if m.get('subscription') is not None and m['subscription'] not in SUBSCRIPTIONS:
        out.append('subscription %r not in %s' % (m['subscription'], ', '.join(SUBSCRIPTIONS)))
    return out


def refused(r, ad=None):
    """{key: reason} of the entries the policy refuses."""
    ad = ad if ad is not None else adapters()
    out = {}
    for k, m in r.get('models', {}).items():
        p = entry_problems(r, k, m, ad)
        if p:
            out[k] = '; '.join(p)
    return out


def roles(r):
    """role -> allowed levels, from models.json `roles` (defaults filled in). A role that allows a level the policy
    forbids for it (ROLES_ALLOWED) stops the program: tiers are never reshuffled by configuration."""
    out = {k: list(v) for k, v in ROLES_DEFAULT.items()}
    for role, lv in ((r or {}).get('roles') or {}).items():
        if role not in ROLES_ALLOWED:
            sys.exit('models.json roles: unknown role %r (known: %s)' % (role, ', '.join(ROLES_ALLOWED)))
        bad = sorted(set(lv) - ROLES_ALLOWED[role])
        if bad or not lv:
            sys.exit('models.json roles.%s = %s breaks the tier policy (allowed: %s). Tier 0 only takes the plan roles '
                     '(pre-mortem, plan review, milestone review), Tier 1 coordinates, backs the plan roles up and runs '
                     'the Express lane, ticket reviews are Tier 2, implementation and fixes Tier 2 or Tier 3, Tier 4 only '
                     'trivial tasks.' % (role, lv, sorted(ROLES_ALLOWED[role])))
        out[role] = list(lv)
    # Planning is Tier 0 first (2026-11-25). A models.json written before that date lists the plan roles as [1] (the
    # old template default, not an owner's choice): Tier 0 is put in front of it. `"plan_tier0": false` keeps Tier 1.
    for role in PLAN_ROLES:
        if (r or {}).get('plan_tier0', True) is False:
            out[role] = [x for x in out[role] if x != 0] or [1]
        elif 0 not in out[role]:
            out[role] = [0] + out[role]
    impl = min(out['implement'])
    out['escalate'] = [max(2, impl - 1)]  # one level up, never Tier 1
    return out


def role_of(pool_name):
    role = POOL_ROLE.get(pool_name)
    if not role:
        sys.exit('unknown pool or role %r (known: %s)' % (pool_name, ', '.join(sorted(POOL_ROLE))))
    return role


def account_key(m, a):
    """`<cli>/<account>`: the unit a quota belongs to."""
    return '%s/%s' % (m['cli'], account_of(m, a))


def detect_coordinator(ad=None):
    """(cli, account) of the coordinator session this process runs under, or None. $AUTOPILOT_COORDINATOR
    (`<cli>` or `<cli>/<account>`) wins; else the first adapter whose `coordinator_env` variable is set in this
    process (Claude Code sets CLAUDECODE, ...), with the account its `account_env` gives in this process (unset = the
    CLI's default home). Every bin/ script runs as a child of the coordinator, so it inherits that environment."""
    ad = ad if ad is not None else adapters()
    forced = os.environ.get('AUTOPILOT_COORDINATOR', '').strip()
    if forced:
        cli, _, acct = forced.partition('/')
        a = ad.get(cli)
        if acct or not a:
            return cli, acct or 'default'
        return cli, session_account(a)
    for name, a in sorted(ad.items()):
        if any(os.environ.get(v) for v in a.get('coordinator_env', [])):
            return name, session_account(a)
    return None


def session_account(a):
    """The account label of this process for an adapter: its `account_env` as set here (unset = default)."""
    k = a.get('account_env')
    v = os.environ.get(k) if k else None
    return account_of({'cli': a['name'], 'model': '', 'env': {k: v}} if v else {'cli': a['name'], 'model': ''}, a)


_COORD = {}


def coordinator_account(r=None, repo=None, ad=None):
    """(cli, account) to protect: detected from this process (see detect_coordinator), else the one recorded in the
    project's state.json `coordinator_account` at setup (`run-model whoami --record`), else None. Never configured in
    models.json: starting the coordinator from another account protects that one and frees the previous one."""
    if 'v' not in _COORD:
        v = detect_coordinator(ad)
        if not v:
            repo = repo or find_repo(required=False)
            ca = (load_state(repo) if repo else {}).get('coordinator_account') or {}
            v = (ca['cli'], ca.get('account') or 'default') if ca.get('cli') else None
        _COORD['v'] = v
    return _COORD['v']


def on_coordinator_account(r, m, a=None, ca=None):
    """True for an entry on the coordinator's own account: same CLI and same account as `coordinator_account`. Keyed on
    the exact account, never on the vendor: another login of the same CLI is a normal account."""
    ca = ca or coordinator_account(r)
    if not ca or m.get('cli') != ca[0]:
        return False
    a = a or adapters().get(m['cli'])
    return bool(a) and account_of(m, a) == ca[1]


def project_capacities(repo=None):
    """state.json `capacity` of the current project: {"<key>": n}. Overrides the roster `capacity` of that key in
    this project's draws only."""
    repo = repo or find_repo(required=False)
    return (load_state(repo) if repo else {}).get('capacity') or {}


def project_excludes(repo=None):
    """state.json `exclude` of the current project: {"<key>" | "<cli>/<account>" | "<cli>": "<reason>"}."""
    repo = repo or find_repo(required=False)
    return (load_state(repo) if repo else {}).get('exclude') or {}


def excluded_reason(r, k, m, a, pex=None):
    """Why an entry is never selected (owner's choice), or None."""
    if m.get('excluded'):
        return str(m['excluded'])
    if m.get('subscription') == 'reserved':
        return 'reserved by the owner'
    pex = project_excludes() if pex is None else pex
    for x in (k, account_key(m, a) if a else None, m.get('cli')):
        if x and x in pex:
            return 'project exclude %s: %s' % (x, pex[x])
    return None


def selectable(m):
    return not m.get('excluded') and m.get('subscription') != 'reserved'


_WHICH = {}


def installed(a):
    """The adapter's binary resolves to a real executable on PATH (a shell alias or function wrapping a removed
    binary does not count: run-model runs the binary, never the user's shell)."""
    b = a.get('binary', a.get('name'))
    if b not in _WHICH:
        exe = shutil.which(b)
        _WHICH[b] = bool(exe and os.path.isfile(os.path.realpath(exe)) and os.access(os.path.realpath(exe), os.X_OK))
    return _WHICH[b]


SUB_WEIGHT = {'paid': 1.0, 'paid?': 0.7, 'free': 0.25}


def credit_left(r, acct):
    """Fraction of credit left on an account (0..1) from the latest `run-model usage` reading (models.json `usage_seen`,
    the most used window wins), or None when unknown or older than 6 h."""
    u = ((r or {}).get('usage_seen') or {}).get(acct) or {}
    if u.get('used') is None or not u.get('at') or (now() - parse_time(u['at'])).total_seconds() > 6 * 3600:
        return None
    return max(0.0, min(1.0, (100 - float(u['used'])) / 100))


def usage_applies(m, a):
    """Whether the account's usage reading covers this model: an adapter with `usage.window_groups` tracks only the
    models those patterns match (opencode: the OpenCode Go allowance, not a Z.ai plan or free models in the same home)."""
    groups = ((a or {}).get('usage') or {}).get('window_groups')
    return not groups or any(re.search(mr, str(m.get('model', '')), re.I) for mr in groups.values())


def weight(r, m, acct, capacity=None, a=None):
    """Draw weight of a candidate: its subscription (paid > paid? > free) times the remaining total usage of its
    subscription: the fraction of credit left on its account (unknown = neutral 0.5, near exhaustion = almost never)
    times the plan's relative size (models.json `capacity`, default 1; e.g. 12 for a plan with 12x the usage of the
    smallest one; a project's state.json `capacity` {"<key>": n} overrides it for that project). A big plan at half credit is drawn more often than a small plan at half credit, so every paid
    subscription is spent in proportion to what it has left before its reset."""
    left = credit_left(r, acct) if usage_applies(m, a) else None
    w = 0.5 if left is None else (0.02 if left < 0.1 else left)
    cap = m.get('capacity') if capacity is None else capacity
    return SUB_WEIGHT.get(m.get('subscription'), 0.7) * w * max(0.0, float(cap or 1))


def rng(r=None):
    """Random source of the draws: seeded by $AUTOPILOT_SEED or models.json `seed` for reproducible runs and tests."""
    import random
    seed = os.environ.get('AUTOPILOT_SEED') or (r or {}).get('seed')
    return random.Random(seed) if seed not in (None, '') else random.Random()


def candidates(r, name, ad=None):
    """Every key that may take a role (or a legacy pool name): a valid, selectable entry (not `excluded`, not
    `reserved`, not in the project's `exclude`) whose policy level is allowed for the role (Tier 0: the plan roles only)
    and whose CLI is installed. Unordered."""
    ad = ad if ad is not None else adapters()
    role = role_of(name)
    allowed = set(roles(r)[role])
    bad = refused(r, ad)
    pex = project_excludes()
    out = []
    for k, m in r.get('models', {}).items():
        a = ad.get(m.get('cli'))
        if k in bad or not a or excluded_reason(r, k, m, a, pex) or level_of(r, m, a) not in allowed or not installed(a):
            continue
        out.append(k)
    return out


def pool(r, name, ad=None, rand=None):
    """Candidates of a role in draw order: no hand-made preference. Healthy candidates off the coordinator's account
    are drawn at random weighted by `weight` (sampling without replacement: the order is the fallback chain), then the
    cooling ones (earliest reset first), then the coordinator's own account last: only for cheap roles (implement,
    fix, trivial), and for Tier 1/2 roles only when the role has no other candidate at all. With models.json
    `coordinator_as_peer: true` (owner's choice) the coordinator's account is drawn like any other account in every
    role. run-model still checks the coordinator's remaining quota (`coordinator_reserve`) before using it.
    A plan role (Tier 0, then Tier 1) keeps its tiers apart: every healthy Tier 0 candidate comes before the first
    Tier 1 one, so Tier 1 runs only when no Tier 0 is eligible and healthy (the logged fallback)."""
    ad = ad if ad is not None else adapters()
    role = role_of(name)
    rand = rand or rng(r)
    t = now()
    live, cooling, coord = [], [], []
    pcap = project_capacities()
    for k in candidates(r, name, ad):
        m = r['models'][k]; a = ad[m['cli']]
        if on_coordinator_account(r, m, a) and not r.get('coordinator_as_peer'):
            coord.append(k); continue
        h = r.get('health', {}).get(k)
        if h and parse_time(h['until']) > t:
            cooling.append((h['until'], k))
        else:
            live.append((weight(r, m, account_key(m, a), pcap.get(k), a), k))
    order = []
    while live:
        tot = sum(w for w, _ in live)
        x = rand.random() * tot
        for i, (w, k) in enumerate(live):
            x -= w
            if x <= 0 or i == len(live) - 1:
                order.append(k); live.pop(i); break
    if role in PLAN_ROLES:  # stable: the weighted draw order is kept inside each tier
        order.sort(key=lambda k: level_of(r, r['models'][k], ad[r['models'][k]['cli']]))
    order += [k for _, k in sorted(cooling)]
    if coord and (role in CHEAP_ROLES or not order):
        order += coord
    return order


def pools(r, ad=None):
    ad = ad if ad is not None else adapters()
    return {role: pool(r, role, ad) for role in list(ROLES_DEFAULT) + ['escalate']}


def pick_reviewers(reg, pool_names, k, excluded, ad=None):
    """k healthy keys of k distinct vendors from the roles' candidates: the first drawn at random (weighted, see
    `pool`), each next one drawn among the remaining candidates of another vendor. Never relaxes the vendor rule nor
    the tier: returns fewer than k when the vendors are not there (the caller waits or alerts)."""
    ad = ad or adapters()
    rand = rng(reg)
    pick, vendors = [], []
    for x in dict.fromkeys(x for p in pool_names for x in pool(reg, p, ad, rand)):
        m = reg['models'].get(x)
        if not m or not healthy(reg, x) or x in excluded:
            continue
        v = vendor_of(m, ad.get(m['cli']))
        if v in vendors:
            continue
        vendors.append(v); pick.append(x)
        if len(pick) == k:
            break
    return pick, vendors


def vendor_ready_at(reg, pool_names, k, excluded, ad=None):
    """When k distinct vendors of the roles' candidates (minus `excluded`) will be healthy: now when they are, the
    k-th earliest per-vendor cooldown end otherwise, None when fewer than k vendors exist at all (configuration)."""
    ad = ad or adapters()
    t = now(); best = {}
    for x in dict.fromkeys(x for p in pool_names for x in candidates(reg, p, ad)):
        if x in excluded:
            continue
        m = reg['models'][x]
        if role_of(pool_names[0]) not in CHEAP_ROLES and not reg.get('coordinator_as_peer') and on_coordinator_account(reg, m, ad.get(m['cli'])):
            continue
        h = reg.get('health', {}).get(x)
        until = parse_time(h['until']) if h and parse_time(h['until']) > t else t
        v = vendor_of(m, ad.get(m['cli']))
        best[v] = min(best.get(v, until), until)
    ends = sorted(best.values())
    return ends[k - 1] if len(ends) >= k else None


def raise_alert(repo, kind, key, title, message, details=None):
    """Raise (or refresh) one CRITICAL alert outside run-model's own recomputed set (e.g. a review that cannot find two
    Tier-2 vendors, the coordinator's quota reserve). It stays until resolved by `resolve_alert` and acknowledged.
    Prints the `CRITICAL:` line; a new alert also posts a Linear project update when the project is known."""
    t = now()

    def fn(al):
        cur = next((a for a in al if a['kind'] == kind and a['key'] == key and not a.get('resolved_at')), None)
        if cur:
            cur.update(message=message, details=details or {}, updated_at=t.isoformat()); return cur, False
        al.append({'id': '%s-%s' % (t.strftime('%Y%m%d-%H%M'), re.sub(r'[^\w.-]+', '-', key)), 'level': 'CRITICAL', 'kind': kind,
                   'key': key, 'at': t.isoformat(), 'title': title, 'message': message, 'details': details or {}})
        return al[-1], True
    a, new = update_alerts(repo, fn)
    print('CRITICAL: %s (alert %s; bin/alert list)' % (message, a['id']), file=sys.stderr)
    pid = (load_state(repo) if repo else {}).get('project_id') or ''
    if new and pid and not pid.startswith('<'):
        p = subprocess.run([os.path.join(HERE, 'linear'), 'project-update', pid, '%s\n\n%s\n\nRaised at %s.' % (title, message, a['at'][:16])],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        update_alerts(repo, lambda al: [x.__setitem__('linear', 'posted' if p.returncode == 0 else (p.stderr or p.stdout)[-200:]) for x in al if x['id'] == a['id']])
    return a


def resolve_alert(repo, kind, key):
    if not os.path.exists(alerts_path(repo)):
        return
    t = now().isoformat()
    update_alerts(repo, lambda al: [a.__setitem__('resolved_at', t) for a in al if a['kind'] == kind and a['key'] == key and not a.get('resolved_at')])


# --- ticket shape (plan time) ------------------------------------------------------------------
# Plan time is where large tickets are prevented. A ticket of size L took 18 rounds (22 files,
# +2051/-638 lines) while parallel tickets edited the same files. The plan is where it is prevented.

TICKET_SIZES = {'XS': 0.5, 'S': 1.0, 'M': 2.0, 'L': 3.0, 'XL': 5.0}
MAX_TICKET_UNITS = 2.0       # M: one concern, about 400 changed lines at most
MAX_TICKET_LINES = 400       # the same cap in lines, for a ticket that declares `lines` (non-mechanical changed lines)
MAX_TICKET_TOUCHES = 8       # files or modules one ticket may change
# Mechanical work (2026-11-25): data files, deletions, renames, generated output and one-line repoints are not what
# the size cap protects against (a reviewer reads a pattern, not every line). A ticket with `"mechanical": true` is
# all of that kind: no size cap and no `touches` count cap. A mixed ticket declares `lines` (the lines someone has to
# think about) and `mechanical_lines` (the rest): only `lines` counts. The plan review checks the claim.
# Lanes (2026-11-25): the process is sized to the work before anything else runs (`spec_lane`, bin/milestone add).
LANES = ('express', 'standard', 'full')
EXPRESS_MAX_LINES = 600      # non-mechanical changed lines of the whole spec
STANDARD_MAX_TICKETS = 5
# A risk flag forces the Full lane whatever the size. `risk` in the spec declares them ([] when none applies; a spec
# without the key is Full, as every spec was before lanes). The spec text is also scanned (fail closed): a hit the
# planner did not declare counts as declared unless `risk_cleared` gives the reason it does not apply, flag by flag.
RISK_FLAGS = {
    'auth': r'\b(auth(entication|orization|n|z)?|log[- ]?in|sign[- ]?in|oauth|sso|saml|rbac|permissions?|access control|session cookie|jwt)\b',
    # "tokens" alone is not a hit (design tokens, LLM tokens): a credential token is named with its kind, or as an
    # environment variable (FOO_TOKEN), which is matched case-sensitively.
    'secrets': r'\b(secrets?|credentials?|passwords?|api[- ]keys?|private keys?|(access|api|auth|bearer|refresh|session|personal access) tokens?|\.env)\b'
               r'|(?-i:\b[A-Z0-9_]*(TOKEN|SECRET|API_KEY|PASSWORD)[A-Z0-9_]*\b)',
    'data-migration': r'\b(migrations?|migrate[sd]?|backfill|schema change|alter table|drop (table|column)|data loss)\b',
    'payments': r'\b(payments?|billing|invoices?|checkout|charge[sd]?|refunds?|stripe|paddle)\b',
    'irreversible': r'\b(dns|force[- ]push|production deploy|deploy(s|ed)? to prod(uction)?|send(s|ing)? (an? |the )?(e-?mails?|mails?|sms)|'
                    r'publish(es|ed|ing)? (to|on) (npm|pypi|the store)|delete[sd]? (the )?(production|prod|customer|user) data|rm -rf)\b',
}


def spec_lane(spec):
    """The lane of a milestone spec (or of a batch of tickets): how much process the work gets.

      express   at most EXPRESS_MAX_LINES non-mechanical lines in all, every ticket sized in `lines`, no risk flag:
                one ticket, one worktree, one Tier 1 implementer, the full checks, two Tier 1 reviewers of two
                vendors on the final diff in parallel. No pre-mortem, no plan review.
      standard  at most STANDARD_MAX_TICKETS tickets, no risk flag: plan review, no pre-mortem.
      full      anything else, any risk flag, or a spec that does not declare `risk`: pre-mortem and plan review.

    `"lane"` in the spec is the owner's override: a heavier lane is always taken; a lighter one needs `"lane_why"`
    (it goes into the decision) and is refused while a risk flag is active.
    Returns {'lane', 'computed', 'why': [..], 'lines', 'mechanical_lines', 'tickets', 'risk': [active flags],
             'hints': {flag: matched text}, 'errors': [..]}."""
    tickets = spec.get('tickets') or []
    errors, why = [], []
    declared = spec.get('risk')
    cleared = spec.get('risk_cleared') or {}
    if declared is not None and (not isinstance(declared, list) or any(x not in RISK_FLAGS for x in declared)):
        errors.append('risk must be a list of %s ([] when none applies)' % ', '.join(RISK_FLAGS)); declared = None
    if not isinstance(cleared, dict) or any(k not in RISK_FLAGS or not str(v or '').strip() for k, v in cleared.items()):
        errors.append('risk_cleared maps a risk flag (%s) to the reason it does not apply' % ', '.join(RISK_FLAGS)); cleared = {}
    text = '\n'.join([str(spec.get(k) or '') for k in ('name', 'description', 'why', 'plan')] +
                     [str(t.get(k) or '') for t in tickets for k in ('title', 'description')])
    hints = {}
    for flag, rx in RISK_FLAGS.items():
        m = re.search(rx, text, re.I)
        if m and flag not in (declared or []) and flag not in cleared:
            hints[flag] = m.group(0)
    active = sorted(set(declared or []) | set(hints))
    lines = mech = 0; unsized = []
    for t in tickets:
        for k in ('lines', 'mechanical_lines'):
            v = t.get(k)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
                errors.append('%s: %s must be a whole number of changed lines' % (t.get('slug'), k))
        n = t.get('lines') if isinstance(t.get('lines'), int) and not isinstance(t.get('lines'), bool) else None
        ml = t.get('mechanical_lines') if isinstance(t.get('mechanical_lines'), int) else 0
        if t.get('mechanical') is True:
            mech += (n or 0) + ml
        else:
            mech += ml
            if n is None: unsized.append(str(t.get('slug')))
            else: lines += n
    if declared is None:
        computed = 'full'; why.append('the spec declares no `risk` list (write "risk": [] when no flag applies)')
    elif active:
        computed = 'full'
        why.append('risk flag%s: %s' % ('s' if len(active) > 1 else '', ', '.join(
            '%s%s' % (f, (' (the text says "%s"; clear it in risk_cleared with the reason, or keep it)' % hints[f]) if f in hints else '')
            for f in active)))
    elif not unsized and lines <= EXPRESS_MAX_LINES:
        computed = 'express'; why.append('%d non-mechanical lines (max %d), no risk flag' % (lines, EXPRESS_MAX_LINES))
    elif len(tickets) <= STANDARD_MAX_TICKETS:
        computed = 'standard'
        why.append('%d ticket%s (max %d), no risk flag' % (len(tickets), '' if len(tickets) == 1 else 's', STANDARD_MAX_TICKETS)
                   + ('; not express: %s' % ('no `lines` on %s' % ', '.join(unsized) if unsized else '%d non-mechanical lines (max %d)' % (lines, EXPRESS_MAX_LINES))))
    else:
        computed = 'full'; why.append('%d tickets (standard takes %d at most)' % (len(tickets), STANDARD_MAX_TICKETS))
    lane = computed
    want = spec.get('lane')
    if want is not None:
        if want not in LANES:
            errors.append('lane must be one of %s' % ', '.join(LANES))
        elif LANES.index(want) > LANES.index(computed):
            lane = want; why.append('lane raised to %s in the spec' % want)
        elif LANES.index(want) < LANES.index(computed):
            if active or declared is None:
                errors.append('lane %r is refused: %s' % (want, why[0]))
            elif not str(spec.get('lane_why') or '').strip():
                errors.append('lane %r is lighter than the computed lane %r: give the owner\'s reason in "lane_why"' % (want, computed))
            elif want == 'express' and unsized:
                errors.append('lane express needs `lines` on every ticket (missing: %s)' % ', '.join(unsized))
            else:
                lane = want; why.append('lane lowered to %s in the spec: %s' % (want, str(spec['lane_why']).strip()))
    return {'lane': lane, 'computed': computed, 'why': why, 'lines': lines, 'mechanical_lines': mech,
            'tickets': len(tickets), 'risk': active, 'hints': hints, 'errors': errors}


def express_spec(spec):
    """The spec of an Express change as the one ticket it runs as: the tickets of the spec become its ordered steps
    (one implementer, one worktree, one review of the final diff). The step `CHECKS:` lines are joined into the
    ticket's one `CHECKS:` line. Blockers outside the spec are kept."""
    tickets = spec.get('tickets') or []
    if len(tickets) == 1 and tickets[0].get('express'):
        return spec
    slugs = [t.get('slug') for t in tickets]
    checks, fast, body = [], [], []
    for i, t in enumerate(tickets, 1):
        d = str(t.get('description') or '')
        for key, acc in (('CHECKS', checks), ('CHECKS_FAST', fast)):
            for m in re.finditer(r'^%s:(.*)$' % key, d, re.M):
                if m.group(1).strip() and m.group(1).strip() not in acc: acc.append(m.group(1).strip())
        d = re.sub(r'^(CHECKS(?:_FAST)?):', lambda m: 'Step check (%s):' % m.group(1).lower(), d, flags=re.M)
        body.append('## Step %d: %s\n\n%s' % (i, t.get('title') or t.get('slug'), d.strip()))
    head = ('Express lane: one change, done in the order of the steps below, in this one worktree. Finish each step '
            'and run its check before the next one.\n\n')
    desc = head + '\n\n'.join(body) + ('\n\nCHECKS: ' + ' && '.join('(%s)' % c for c in checks) if checks else '') \
        + ('\nCHECKS_FAST: ' + ' && '.join('(%s)' % c for c in fast) if fast and len(fast) == len(tickets) else '')
    one = {'slug': spec.get('id') or slugs[0], 'title': spec.get('batch') or spec.get('name') or slugs[0], 'description': desc,
           'estimate': 'M', 'express': True, 'priority': min([t.get('priority', 3) for t in tickets] or [3]),
           'lines': sum(t.get('lines') or 0 for t in tickets),
           'touches': sorted({str(p) for t in tickets for p in (t.get('touches') or [])}),
           'blocked_by': sorted({b for t in tickets for b in (t.get('blocked_by') or []) if b not in slugs}),
           'labels': sorted({x for t in tickets for x in (t.get('labels') or [])})}
    ideas = [t['from_idea'] for t in tickets if t.get('from_idea')]
    if ideas: one['from_idea'] = ideas[0]
    return dict(spec, tickets=[one])
SHARED_DIR_SEGMENTS = {'tests', 'test', '__tests__', 'docs'}  # any path segment, not only the repo root
SHARED_FILE_GLOBS = ('*.test.*', '*.spec.*', 'test_*.py', '*_test.py')
SHARED_PREFIXES = ('e2e/artifacts',)  # side-by-side artifacts are not a collision


def ticket_units(v):
    if isinstance(v, str) and v.strip().upper() in TICKET_SIZES:
        return TICKET_SIZES[v.strip().upper()]
    return float(v)


def _overlap(a, b):
    """Two touched paths collide when equal or when one is a directory prefix of the other."""
    a, b = a.strip().rstrip('/'), b.strip().rstrip('/')
    return a == b or a.startswith(b + '/') or b.startswith(a + '/')


def ticket_touches(repo):
    """{issue identifier: [touched paths]} for the project's tickets.

    Read from each milestone spec (`.maxxfactory/plan/milestones/*/spec.json`, slugs mapped to identifiers by the
    `tickets.created.json` next to it), then overridden by the `Touches ...:` line of the ticket file
    (`.maxxfactory/tickets/<ISSUE>.md`), which a coordinator decision may have changed since the plan. Tickets with
    neither are absent: callers must not treat a missing entry as "touches nothing".
    """
    out = {}
    for spec in glob.glob(pdir(repo, 'plan', 'milestones', '*', 'spec.json')):
        try:
            tickets = json.load(open(spec)).get('tickets') or []
            created = json.load(open(os.path.join(os.path.dirname(spec), 'tickets.created.json'))).get('tickets') or {}
        except (OSError, ValueError):
            continue
        for t in tickets:
            ident = (created.get(t.get('slug')) or {}).get('identifier')
            if ident and isinstance(t.get('touches'), list):
                out[ident] = [str(x) for x in t['touches'] if str(x).strip()]
    for f in glob.glob(pdir(repo, 'tickets', '*.md')):
        try:
            m = re.search(r'^Touches[^:\n]*:\s*(.+)$', open(f).read(), re.M)
        except OSError:
            continue
        if m:
            paths = [x.strip().strip('`').strip() for x in m.group(1).split(',')]
            paths = [x for x in paths if x and ' ' not in x]
            if paths:
                out[os.path.basename(f)[:-3]] = paths
    return out


def needless_blockers(repo, blockers, open_items, needs_output=None):
    """[(ticket, blocker)] pairs among open tickets whose touched files never collide.

    A blocker that changes none of the ticket's files (shared test and docs paths aside) is either an output the
    ticket needs or only an ordering preference; the second kind keeps a lane idle for nothing. Pairs the
    coordinator checked and kept are listed in state.json `needs_output` ({ticket: [blockers]}) and skipped.
    """
    touches, pairs, keep = ticket_touches(repo), [], needs_output or {}
    for t in open_items:
        for b in blockers.get(t) or []:
            if b in (keep.get(t) or []):
                continue
            if b not in open_items or t not in touches or b not in touches:
                continue
            ta = [p for p in touches[t] if not shared_touch(p)]
            tb = [p for p in touches[b] if not shared_touch(p)]
            if ta and tb and not any(_overlap(x, y) for x in ta for y in tb):
                pairs.append((t, b))
    return pairs


def shared_touch(path):
    """A path parallel tickets may both change.

    Shared at any depth when a segment is tests, test, __tests__ or docs (so web/test/x.test.tsx and
    packages/a/tests/ are shared), or when the file name matches *.test.*, *.spec.*, test_*.py or *_test.py.
    """
    parts = [p for p in str(path).strip().replace('\\', '/').split('/') if p not in ('', '.')]
    if not parts:
        return False
    if any(seg in SHARED_DIR_SEGMENTS for seg in parts):
        return True
    name = parts[-1]
    if any(fnmatch.fnmatch(name, g) for g in SHARED_FILE_GLOBS):
        return True
    raw = '/'.join(parts)
    return any(raw == pre or raw.startswith(pre + '/') for pre in SHARED_PREFIXES)


def ticket_shape_errors(tickets, deps=None):
    """Errors that make a ticket list unfit to run: too big, no declared footprint, or two tickets
    that may run in parallel while changing the same file.

    `deps` maps slug -> slugs it waits on (inside this list); tickets ordered by it never run in
    parallel, so their shared files are allowed. A test or docs path is never a collision: any
    directory named tests, test, __tests__ or docs, or a file named *.test.*, *.spec.*, test_*.py
    or *_test.py.
    """
    errs = []
    by = {t.get('slug'): t for t in tickets}
    deps = deps if deps is not None else {s: [b for b in (t.get('blocked_by') or []) if b in by] for s, t in by.items()}
    for s, t in by.items():
        try:
            u = ticket_units(t.get('estimate', 1))
        except (TypeError, ValueError):
            continue  # the caller reports a bad estimate
        # Mechanical tickets and the one ticket of an Express change are outside the size and touches caps (see above).
        free = t.get('mechanical') is True or t.get('express') is True
        if u > MAX_TICKET_UNITS and not free:
            errs.append(f'{s}: size {t.get("estimate")} is larger than M: split it into tickets of one concern '
                        f'(about 400 changed lines each), chained with blocked_by where they share files; a ticket '
                        f'that is only mechanical (data files, deletions, renames, one-line repoints) says "mechanical": true')
        n = t.get('lines')
        if isinstance(n, int) and not isinstance(n, bool) and n > MAX_TICKET_LINES and not free:
            errs.append(f'{s}: {n} non-mechanical lines (max {MAX_TICKET_LINES}): split it; mechanical lines go in '
                        f'`mechanical_lines` and do not count')
        touches = t.get('touches')
        if not isinstance(touches, list) or not [p for p in touches if str(p).strip()]:
            errs.append(f'{s}: `touches` is required: the files or modules this ticket changes (e.g. '
                        f'["api/app.py", "web/src/components/drawer/"])')
        elif len(touches) > MAX_TICKET_TOUCHES and not free:
            errs.append(f'{s}: touches {len(touches)} files or modules (max {MAX_TICKET_TOUCHES}): split it')
        # The pipeline runs a ticket's CHECKS line as a shell command; prose there ("just check (and the named
        # tests: x.py)") sent an approved ticket to triage on 2026-11-20 with a bash syntax error.
        for m in re.finditer(r'^(CHECKS(?:_FAST)?):(.*)$', str(t.get('description') or ''), re.M):
            cmd = m.group(2).strip()
            if cmd and subprocess.run(['bash', '-n', '-c', cmd], capture_output=True).returncode != 0:
                errs.append(f'{s}: the {m.group(1)} line is not a shell command (`{cmd[:80]}`): write the exact '
                            f'command, and put any explanation on another line')

    def ancestors(s, seen=None):
        seen = set() if seen is None else seen
        for b in deps.get(s, []):
            if b not in seen:
                seen.add(b); ancestors(b, seen)
        return seen

    anc = {s: ancestors(s) for s in by}
    slugs = list(by)
    for i, a in enumerate(slugs):
        for b in slugs[i + 1:]:
            if a in anc[b] or b in anc[a]:
                continue
            ta = [p for p in by[a].get('touches') or [] if not shared_touch(p)]
            tb = [p for p in by[b].get('touches') or [] if not shared_touch(p)]
            hit = sorted({x for x in ta for y in tb if _overlap(str(x), str(y))})
            if hit:
                errs.append(f'{a} and {b} can run in parallel but both change {", ".join(hit)}: order them with '
                            f'blocked_by, or split so each file has one owner per stage')
    return errs


def worktree_processes(path):
    """Process ids whose working directory is `path` or below it (servers, browsers, test runners a
    ticket's checks started there). One `lsof` pass over every process's cwd; empty when lsof fails."""
    root = os.path.realpath(path).rstrip('/') + '/'
    try:
        out = subprocess.run(['lsof', '-a', '-d', 'cwd', '-Fpn'], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids, pid = [], None
    for line in out.splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
        elif line.startswith('n') and pid and pid != os.getpid():
            cwd = os.path.realpath(line[1:]).rstrip('/') + '/'
            if cwd.startswith(root):
                pids.append(pid)
    return pids


def reap_worktree(path, sig=signal.SIGTERM):
    """Stops every process running in a worktree, with its process group. Called before a worktree is
    removed and before a check is restarted: a removed worktree must not leave servers, browsers or a
    hung test run behind (2026-11-20: 13 leaked next-server processes and 7 orphaned checks drove the
    load past 300 and blocked every check for an hour). Returns the pids signalled."""
    pids = worktree_processes(path)
    inside, done = set(pids), []
    me = os.getpgid(0)
    for pid in pids:
        try:
            pg = os.getpgid(pid)
            # A whole group goes only when its leader also runs in the worktree and it is not our own group:
            # a stray process must never take an unrelated group (the coordinator's shell, a test runner) with it.
            if pg in inside and pg != me:
                os.killpg(pg, sig)
            else:
                os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            continue
        done.append(pid)
    return done


# ---------- CI on the project branch: nothing runs while the PR is a draft ----------

CI_EVENTS = ('push', 'pull_request', 'pull_request_target')


def ci_findings(repo, st=None):
    """What breaks the rule "the project's PR is a draft and no CI run starts on its pushes until it is ready to
    merge" (2026-11-22: a workflow ran, failed and mailed the owner on every push of a draft PR, one push per ticket).
    Returns a list of `CI: ...` lines (empty: clean), or None when it cannot tell (push off, no `gh`, not GitHub,
    network). Looks at the open PR of state.json `branch` and at the workflow runs of the last pushed commit; a run
    that was skipped costs nothing and is fine. state.json `pr_ready: true` (set at wrap-up, once the owner said the
    work is ready to merge) turns the rule off: CI is then meant to run."""
    st = load_state(repo) if st is None else st
    br = st.get('branch')
    gh = os.environ.get('AUTOPILOT_GH') or shutil.which('gh')
    if not st.get('push') or not br or st.get('pr_ready') or not gh or gh == 'off':
        return None

    def run(*a):
        try:
            p = subprocess.run([gh] + list(a), cwd=repo, capture_output=True, text=True, timeout=40, stdin=subprocess.DEVNULL)
            return json.loads(p.stdout) if p.returncode == 0 else None
        except (subprocess.SubprocessError, ValueError, OSError):
            return None
    prs = run('pr', 'list', '--head', br, '--state', 'open', '--json', 'number,isDraft,url')
    runs = run('run', 'list', '--branch', br, '--limit', '40', '--json', 'workflowName,event,conclusion,status,headSha,url')
    if prs is None or runs is None:
        return None
    out = ['CI: PR #%s of %s is not a draft: `gh pr ready --undo %s` (a PR is marked ready only when the work is ready to merge)'
           % (p.get('number'), br, p.get('number')) for p in prs if not p.get('isDraft')]
    head = git(repo, 'rev-parse', '-q', '--verify', 'refs/remotes/origin/' + br).stdout.strip()
    seen = set()
    for r in runs:
        if r.get('headSha') != head or r.get('event') not in CI_EVENTS or r.get('conclusion') == 'skipped':
            continue
        k = (r.get('workflowName'), r.get('event'))
        if k not in seen:
            seen.add(k)
            out.append('CI: workflow "%s" ran on the last push of %s (%s, %s): %s' % (
                k[0], br, k[1], r.get('conclusion') or r.get('status') or 'running', r.get('url') or ''))
    return out


# ---------- worktree garbage collection ----------

GC_EMPTY_HOURS = 24  # an untouched worktree nobody started (no change, no commit) is kept this long


def gc_worktrees(repo, dry=False, now=None):
    """Removes the worktrees no ticket needs any more, so agents, checks, the indexer and the disk only see the ones
    in flight. Only worktrees under the project's worktrees directory (`<repo>-wt`, and the directory an older
    state.json recorded) are looked at; one that is in flight, queued or locked is never touched. Removed: a worktree whose ticket is in `done` (work found in it is saved first as a patch
    in .maxxfactory/gc/), and one with no change and no commit of its own for GC_EMPTY_HOURS. A worktree that is not in
    flight but holds work is never removed: it is reported as an orphan for the coordinator to merge or drop.
    Ticket branches (`maxxfactory/*`, `autopilot/*`) left without a worktree go too when their ticket is done or they hold no commit.
    Returns [(action, path or branch, detail)] with action in removed, branch, orphan, pruned."""
    st = load_state(repo)
    now = now or time.time()
    root = os.path.realpath(worktrees_dir(repo)).rstrip('/') + '/'
    base = st.get('branch') or 'HEAD'
    inflight = st.get('inflight') or {}
    done = set(st.get('done') or [])
    keep_ids = set(inflight) | set(st.get('queue') or [])
    keep_paths = {os.path.realpath((v or {}).get('wt') or os.path.join(root, t)) for t, v in inflight.items()
                  if isinstance(v, dict) or v is None}
    out = []
    if not dry:
        p = git(repo, 'worktree', 'prune', '-v')
        out += [('pruned', l.strip(), '') for l in (p.stdout + p.stderr).splitlines() if l.strip()]
    entries, cur = [], {}
    for line in git(repo, 'worktree', 'list', '--porcelain').stdout.splitlines() + ['']:
        if not line:
            if cur:
                entries.append(cur)
            cur = {}
        else:
            k, _, v = line.partition(' ')
            cur[k] = v
    # the project branch and the branch of the main checkout are never collected
    used = {base} | {(e.get('branch') or '').replace('refs/heads/', '') for e in entries[:1]}
    for e in entries[1:]:  # the first entry is the main checkout
        wt = os.path.realpath(e['worktree'])
        br = (e.get('branch') or '').replace('refs/heads/', '')
        used.add(br)
        t = os.path.basename(wt)
        if not in_worktrees_dir(repo, wt, st) or not os.path.isdir(wt):
            continue
        if wt in keep_paths or t in keep_ids or 'locked' in e:
            continue
        dirty = [l for l in git(wt, 'status', '--porcelain').stdout.splitlines() if l.strip()]
        ahead = int(git(wt, 'rev-list', '--count', '%s..HEAD' % base).stdout.strip() or 0)
        try:
            idle = now - max(os.stat(wt).st_mtime, os.stat(os.path.join(wt, '.git')).st_mtime)
        except OSError:
            idle = 0
        if t in done:
            why = 'ticket done'
        elif not dirty and not ahead and idle > GC_EMPTY_HOURS * 3600:
            why = 'no change and no commit for %d h' % (idle // 3600)
        else:
            if dirty or ahead:
                out.append(('orphan', wt, 'not in flight, %d commit(s) and %d changed file(s) of its own, idle %d h: '
                                          'merge it, put it back in flight, or remove it' % (ahead, len(dirty), idle // 3600)))
            continue
        if dry:
            out.append(('removed', wt, why + ' (dry run)')); continue
        if dirty or ahead:  # never lose work silently: the whole difference with the project branch, as one patch
            git(wt, 'add', '-A')
            mb = git(wt, 'merge-base', base, 'HEAD').stdout.strip() or 'HEAD'
            patch = subprocess.run(['git', '-C', wt, 'diff', '--cached', '--binary', mb], capture_output=True).stdout
            if patch:
                d = pdir(repo, 'gc'); os.makedirs(d, exist_ok=True)
                f = os.path.join(d, '%s-%s.patch' % (t, time.strftime('%Y%m%d-%H%M%S', time.localtime(now))))
                with open(f, 'wb') as fh:
                    fh.write(patch)
                why += ', work saved in %s' % os.path.relpath(f, repo)
        reap_worktree(wt)
        g = git(repo, 'worktree', 'remove', '--force', wt)
        if g.returncode != 0:
            out.append(('orphan', wt, 'could not be removed: %s' % (g.stderr or g.stdout).strip()[-200:])); continue
        out.append(('removed', wt, why))
        if br.startswith(TICKET_BRANCH_PREFIXES):
            git(repo, 'branch', '-q', '-D', br); used.discard(br)
            out.append(('branch', br, 'worktree removed'))
    for br in git(repo, 'for-each-ref', '--format=%(refname:short)',
                  *('refs/heads/' + x for x in TICKET_BRANCH_PREFIXES)).stdout.split():
        t = br.split('/', 1)[1]
        if br in used or t in keep_ids:
            continue
        ahead = int(git(repo, 'rev-list', '--count', '%s..%s' % (base, br)).stdout.strip() or 0)
        if t in done or not ahead:
            if not dry:
                git(repo, 'branch', '-q', '-D', br)
            out.append(('branch', br, ('ticket done' if t in done else 'no commit of its own') + (' (dry run)' if dry else '')))
    return out


# ---------- run state: is the run moving, done, stuck, or waiting on the owner? ----------
# 2026-11-22: a run sat for hours with one ticket held by the coordinator (stage `hold`, outside the clock), two
# tickets that only the owner could unblock, `wait-approval` blocked on a pipeline with nothing to approve, and an
# ETA that moved forward at every reading. Nothing said "stuck" or "waiting on you". The verdict is computed here,
# from facts (state.json, the clock's lock, live jobs and processes), never from what the coordinator believes.

PIPELINE_DRIVEN = ('starting', 'implement', 'merge', 'rebase', 'review', 'final', 'stacked')
RUN_STATES = ('RUNNING', 'DONE', 'STUCK', 'WAITING ON OWNER', 'STOPPED')


def clock_alive(repo):
    """True while a `pipeline run` holds this project's lock."""
    p = pdir(repo, 'pipeline', 'run.lock')
    if not os.path.exists(p):
        return False
    try:
        with open(p, 'a+') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass
    return False


def live_bg_jobs(repo):
    """Names of the bgrun jobs of this project that still run (the clock itself excluded)."""
    d, out = pdir(repo, 'jobs'), []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        try:
            j = read_json(os.path.join(d, name))
            if j.get('status') != 'running' or j.get('name') == 'pipeline':
                continue
            os.kill(int(j['pid']), 0)
            out.append(j['name'])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def open_tickets(st):
    """(in flight, queued) ticket ids in scope: ideas never count, a ticket is listed once."""
    ideas = st.get('ideas') or {}
    idea_set = set(ideas.get('issues') or [])
    inflight = {t: v for t, v in (st.get('inflight') or {}).items() if t not in idea_set}
    done = set(st.get('done') or [])
    raw = list(st.get('queue') or [])
    for m in st.get('milestones') or []:
        if m.get('linear_id') and m.get('linear_id') == ideas.get('linear_milestone_id'):
            continue
        raw += m.get('issues', [])
    queue = [t for t in dict.fromkeys(raw) if t not in idea_set and t not in inflight and t not in done]
    return inflight, queue


def owner_waits(st):
    """{ticket: what the owner must do} for every open ticket that cannot move without the owner: listed in
    state.json `owner_wait` ({ticket: reason}) or `blocked`, or queued behind such a ticket."""
    inflight, queue = open_tickets(st)
    open_set = set(inflight) | set(queue)
    direct = {t: str(r) for t, r in (st.get('owner_wait') or {}).items() if t in open_set}
    for t in st.get('blocked') or []:
        if t in open_set:
            direct.setdefault(t, 'blocked')
    out, blockers = dict(direct), st.get('blockers') or {}
    changed = True
    while changed:
        changed = False
        for t in queue:
            if t in out:
                continue
            for b in blockers.get(t, []):
                if b in out:
                    out[t] = out[b]
                    changed = True
                    break
    return out


def run_state(repo, st=None, procs=None):
    """The verdict on a run: {'state': one of RUN_STATES, 'why': one line, 'live', 'owner', 'stuck', 'line'}.
    RUNNING: at least one ticket is really moving (driven by a live clock, or a job or model run exists for a ticket
    the coordinator drives by hand). DONE: nothing left in scope. WAITING ON OWNER: every ticket left needs the owner.
    STUCK: work is left, nothing moves, and it is not the owner's turn. STOPPED: no clock and nothing in flight (a
    project planned and not started, or a run whose session ended between tickets): the ETA is the plan's."""
    st = load_state(repo) if st is None else st
    inflight, queue = open_tickets(st)
    done = set(st.get('done') or [])
    owner = owner_waits(st)
    pcfg = st.get('pipeline') or {}
    clock = clock_alive(repo)
    jobs = live_bg_jobs(repo)
    if procs is None:
        procs = subprocess.run(['ps', '-ax', '-o', 'command='], capture_output=True, text=True).stdout.splitlines()
    live, stuck = [], []
    for t, v in inflight.items():
        if t in owner:
            continue
        stage = v.get('stage', '?') if isinstance(v, dict) else '?'
        if stage in ('triage', 'stuck'):
            stuck.append('%s %s: waits for the coordinator' % (t, stage))
        elif stage == 'approved' and not pcfg.get('auto_merge'):
            stuck.append('%s approved: waits for the coordinator to merge it' % t)
        elif stage in PIPELINE_DRIVEN or stage == 'approved':
            wt = (v.get('wt') if isinstance(v, dict) else None) or os.path.join(worktrees_dir(repo, st), t)
            if not clock:
                stuck.append('%s %s: the pipeline clock is not running' % (t, stage))
            elif stage != 'starting' and not os.path.isdir(wt):
                stuck.append('%s %s: its worktree is missing (%s)' % (t, stage, wt))
            else:
                live.append('%s %s' % (t, stage))
        else:  # hold, plan, ...: the coordinator drives it by hand, so only a job or a model run proves it moves
            pat = re.compile(r'(?<![A-Za-z0-9-])%s(?![A-Za-z0-9])' % re.escape(t))
            own = any(pat.search(c) and any(os.path.basename(x) in ('run-model', 'review') for x in c.split()[:3])
                      for c in procs)
            if jobs or own:
                live.append('%s %s (%s)' % (t, stage, 'jobs: ' + ', '.join(jobs[:4]) if jobs else 'model run'))
            else:
                stuck.append('%s %s: driven by hand, and no job or model run exists for it' % (t, stage))
    blockers = st.get('blockers') or {}
    ready = [t for t in queue if t not in owner and all(b in done for b in blockers.get(t, []))]
    for t in ready:
        tf = pdir(repo, 'tickets', t + '.md')
        if clock and pcfg.get('auto_start') and os.path.exists(tf):
            live.append('%s starts by itself' % t)
    stopped = bool(ready) and not clock and not live and not [t for t in inflight if t not in owner]
    if ready and not live:
        stuck.append('%d ticket%s ready and not started (%s)' % (len(ready), '' if len(ready) == 1 else 's',
                                                                 ', '.join(ready[:5]) + (', ...' if len(ready) > 5 else '')))
    by_reason = {}
    for t, r in owner.items():
        by_reason.setdefault(r, []).append(t)
    owner_txt = '; '.join('%s (%s)' % (r, ', '.join(ts)) for r, ts in by_reason.items())
    n_open = len(inflight) + len(queue)
    if not n_open:
        state = 'DONE'
        why = '%d/%d tickets done, nothing left to run' % (len(done), len(done))
        if st.get('proposed_milestones'):
            why += '; %d proposed milestone(s) await your approval' % len(st['proposed_milestones'])
    elif live:
        state = 'RUNNING'
        why = ', '.join(live[:6]) + (', ...' if len(live) > 6 else '')
        if stuck:
            why += ' | needs the coordinator: ' + '; '.join(stuck[:3])
        if owner:
            why += ' | waiting on owner: ' + owner_txt
    elif len(owner) == n_open:
        state = 'WAITING ON OWNER'
        why = owner_txt + '. Nothing else can run'
    elif stopped:
        state = 'STOPPED'
        why = '%d ticket%s ready, the pipeline is not running: /maxxfactory-run starts it, /maxxfactory-continue resumes it' % (
            len(ready), '' if len(ready) == 1 else 's')
        if owner:
            why += ' | waiting on owner: ' + owner_txt
    else:
        state = 'STUCK'
        why = '; '.join(stuck[:4]) if stuck else 'tickets are left but none is in flight or ready: check `blockers`'
        if owner:
            why += ' | waiting on owner: ' + owner_txt
    return {'state': state, 'why': why, 'live': live, 'owner': owner, 'stuck': stuck, 'ready': ready,
            'line': 'RUN: %s | %s' % (state, why)}


# ---------- logins (is every account still logged in, and until when) ----------
# 2026-11-22: the coordinator's own Claude login reached its expiry in the middle of the night and the run died with
# it. A login is checked with the CLI's own status command when the adapter declares one (`account_login.status`:
# `argv`, then either `json` keys `logged_in` / `expires_at`, or an `ok` regex on the output), else by its login file.

def login_status(a, home=None):
    """{'logged_in': True | False | None (cannot tell), 'expires_at': datetime | None, 'note': str} for one account
    of a harness. `home` is the account directory (None = the CLI's default account). Nothing secret is read."""
    spec = a.get('account_login') or {}
    st = spec.get('status')
    if st and installed(a):
        env = dict(os.environ)
        k = a.get('account_env')
        if k:
            env.pop(k, None)
            default = os.path.expanduser(a.get('account_default', '')).rstrip('/')
            if home and os.path.realpath(home) != os.path.realpath(default):
                env[k] = home
        try:
            p = subprocess.run([a.get('binary', a['name'])] + list(st['argv']), capture_output=True, text=True, env=env,
                               timeout=st.get('timeout', 30), stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {'logged_in': None, 'expires_at': None, 'note': 'status command failed: %s' % type(e).__name__}
        out = (p.stdout or '') + (p.stderr or '')
        if st.get('json'):
            try:
                d = json.loads(p.stdout[p.stdout.index('{'):])
            except ValueError:
                return {'logged_in': False if p.returncode else None, 'expires_at': None, 'note': 'status output not readable'}
            exp = d.get(st['json'].get('expires_at') or '')
            try:
                exp = parse_time(exp) if exp else None
            except (ValueError, TypeError):
                exp = None
            return {'logged_in': bool(d.get(st['json'].get('logged_in', 'loggedIn'))), 'expires_at': exp, 'note': ''}
        return {'logged_in': p.returncode == 0 and bool(re.search(st.get('ok', '.'), out, re.I)), 'expires_at': None, 'note': ''}
    if spec.get('file') and (home or a.get('account_default')):
        f = os.path.join(home or os.path.expanduser(a['account_default']), spec['file'])
        # a missing file proves nothing: CLIs move their credentials (opencode left auth.json for its own store)
        return {'logged_in': True if os.path.exists(f) else None, 'expires_at': None, 'note': 'login file only'}
    return {'logged_in': None, 'expires_at': None, 'note': 'no login check for this harness'}


def logins(reg=None, ad=None, min_hours=48, repo=None):
    """One row per account the run depends on: every account with a selectable roster entry, plus the coordinator's
    own. `problem` is set when the account is not logged in, or its login expires within `min_hours`."""
    if os.environ.get('AUTOPILOT_LOGIN_CHECK') == 'off':
        return []
    ad = ad or adapters()
    reg = reg if reg is not None else load_reg(warn=False)
    ca = coordinator_account(reg, repo, ad)
    pex = project_excludes(repo) if repo else None
    want = {}  # (cli, account label) -> home
    for k, m in reg.get('models', {}).items():
        a = ad.get(m.get('cli'))
        if not a or excluded_reason(reg, k, m, a, pex):
            continue
        home = explicit_account(m, a)
        want[(m['cli'], account_of(m, a))] = os.path.expanduser(home) if home else None
    if ca and ad.get(ca[0]):
        want.setdefault(ca, os.path.expanduser(ca[1].split('=', 1)[1]) if '=' in ca[1] else None)
    rows, t = [], now()
    for (cli, acc), home in sorted(want.items()):
        s = login_status(ad[cli], home)
        hours = (s['expires_at'] - t).total_seconds() / 3600 if s['expires_at'] else None
        problem = None
        if s['logged_in'] is False:
            problem = 'not logged in'
        elif hours is not None and hours < min_hours:
            problem = 'login expired' if hours <= 0 else 'login expires in %s' % ('%dh' % hours if hours < 72 else '%dd' % (hours / 24))
        rows.append({'cli': cli, 'account': acc, 'home': home, 'coordinator': (cli, acc) == ca, 'logged_in': s['logged_in'],
                     'expires_at': s['expires_at'].isoformat() if s['expires_at'] else None, 'hours_left': hours,
                     'note': s['note'], 'problem': problem})
    return rows


def login_fix(row, ad=None):
    """The command the owner types to log that account in again."""
    a = (ad or adapters())[row['cli']]
    cmd = '%s %s' % (a.get('binary', row['cli']), ' '.join((a.get('account_login') or {}).get('login') or ['login']))
    return '%s=%s %s' % (a['account_env'], row['home'], cmd) if row.get('home') and a.get('account_env') else cmd
