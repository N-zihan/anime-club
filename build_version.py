import subprocess

def get_version():
    try:
        version = subprocess.check_output(
            ['git', 'describe', '--tags', '--abbrev=0'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if version:
            return version
    except Exception:
        pass
    try:
        commit = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if commit:
            return f"dev-{commit}"
    except Exception:
        pass
    return 'dev'

if __name__ == '__main__':
    version = get_version()
    with open('version.txt', 'w') as f:
        f.write(version)