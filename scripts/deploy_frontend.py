#!/usr/bin/env python3
"""Deploy the VK Admin Panel frontend to Yandex Object Storage.

Usage:
    # From project root:
    uv run python scripts/deploy_frontend.py

    # Or via Make:
    make deploy-frontend

Requires:
    - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (Yandex Object Storage static keys)
    - VK_ADMIN_PANEL_BUCKET env var (bucket name, e.g. "la-admin-panel")
    - Node.js / npm installed (for building)

The script:
    1. Reads env vars from .env (root) and .env.production (frontend)
    2. Builds the frontend with `npm run build`
    3. Uploads all files from dist/ to the S3-compatible bucket
    4. Sets Content-Type based on file extension
    5. Configures bucket for public static hosting
"""

import json
import mimetypes
import os
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

# ── Paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / 'frontend' / 'vk-admin-panel'
DIST_DIR = FRONTEND_DIR / 'dist'
ROOT_ENV_FILE = PROJECT_ROOT / '.env'
FRONTEND_ENV_FILE = FRONTEND_DIR / '.env.production'

# ── Config (loaded from env, then fallback to .env files) ────────────
ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL', 'https://storage.yandexcloud.net')
REGION_NAME = 'ru-central1'


def _load_env_file(path: Path) -> dict[str, str]:
    """Load a .env file and return a dict of key-value pairs."""
    if not path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def _get_env(key: str, default: str = '') -> str:
    """Get env var from environment first, then from root .env, then from .env.production."""
    value = os.environ.get(key)
    if value:
        return value
    # Try root .env
    root_vars = _load_env_file(ROOT_ENV_FILE)
    if key in root_vars:
        return root_vars[key]
    # Try frontend .env.production
    frontend_vars = _load_env_file(FRONTEND_ENV_FILE)
    return frontend_vars.get(key, default)


BUCKET_NAME = _get_env('VK_ADMIN_PANEL_BUCKET')
ACCESS_KEY = _get_env('AWS_ACCESS_KEY_ID')
SECRET_KEY = _get_env('AWS_SECRET_ACCESS_KEY')


def _check_prerequisites() -> None:
    """Check that all required tools and env vars are available."""
    missing: list[str] = []

    if not BUCKET_NAME:
        missing.append('VK_ADMIN_PANEL_BUCKET')
    if not ACCESS_KEY:
        missing.append('AWS_ACCESS_KEY_ID')
    if not SECRET_KEY:
        missing.append('AWS_SECRET_ACCESS_KEY')

    if missing:
        print(f'❌ Missing required environment variables: {", ".join(missing)}')
        print('   Set them in your environment or in .env file.')
        sys.exit(1)

    # Check npm
    try:
        subprocess.run(['npm', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print('❌ npm not found. Make sure Node.js is installed.')
        sys.exit(1)


def _build_frontend() -> None:
    """Build the frontend with Vite."""
    print('🔨 Building frontend...')
    env = os.environ.copy()

    # Load .env.production and merge into environment
    env_file_vars = _load_env_file(FRONTEND_ENV_FILE)
    for key, value in env_file_vars.items():
        env[key] = value

    result = subprocess.run(
        ['npm', 'run', 'build'],
        cwd=str(FRONTEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print('❌ Build failed:')
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)

    print('✅ Build successful.')
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            print(f'   {line}')


def _get_s3_client():
    """Create an S3 client for Yandex Object Storage.

    Uses explicit static credentials + region_name for signature v4 signing.
    """
    session = boto3.session.Session()
    return session.client(
        service_name='s3',
        endpoint_url=ENDPOINT_URL,
        region_name=REGION_NAME,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=BotoConfig(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
        ),
    )


def _upload_to_s3() -> None:
    """Upload the dist/ folder to Yandex Object Storage."""
    if not DIST_DIR.exists():
        print(f'❌ Build directory not found: {DIST_DIR}')
        print('   Did the build step succeed?')
        sys.exit(1)

    print(f'☁️  Uploading to s3://{BUCKET_NAME} ...')

    s3 = _get_s3_client()

    # Upload all files
    uploaded = 0
    skipped = 0

    for file_path in sorted(DIST_DIR.rglob('*')):
        if not file_path.is_file():
            continue

        # Relative path inside the bucket
        key = str(file_path.relative_to(DIST_DIR))

        # Detect content type
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            # Default for common web files
            ext = file_path.suffix.lower()
            content_type = {
                '.js': 'application/javascript',
                '.css': 'text/css',
                '.html': 'text/html',
                '.svg': 'image/svg+xml',
                '.png': 'image/png',
                '.ico': 'image/x-icon',
                '.json': 'application/json',
                '.woff2': 'font/woff2',
                '.woff': 'font/woff',
                '.ttf': 'font/ttf',
            }.get(ext, 'application/octet-stream')

        extra_args = {
            'ContentType': content_type,
            'CacheControl': 'public, max-age=31536000, immutable',
        }

        # For index.html — no long cache (needs to be fresh for SPA routing)
        if key == 'index.html':
            extra_args['CacheControl'] = 'no-cache, no-store, must-revalidate'

        try:
            s3.upload_file(
                Filename=str(file_path),
                Bucket=BUCKET_NAME,
                Key=key,
                ExtraArgs=extra_args,
            )
            uploaded += 1
            print(f'   ✅ {key} ({content_type})')
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                print(f'\n❌ Bucket "{BUCKET_NAME}" does not exist.')
                print('   Create it first via Terraform or Yandex Cloud Console.')
                print('   Or add it to terraform/main.tf:')
                print(f'     resource "yandex_storage_bucket" "admin_panel" {{')
                print(f'       bucket = "{BUCKET_NAME}"')
                print(f'       acl    = "public-read"')
                print(f'       website {{')
                print(f'         index_document = "index.html"')
                print(f'         error_document = "index.html"')
                print(f'       }}')
                print(f'     }}')
                sys.exit(1)
            print(f'   ❌ {key}: {e}')
            skipped += 1

    # Configure bucket for static hosting
    print('\n🔓 Configuring bucket for static hosting...')
    try:
        # Disable public access blocks
        s3.put_public_access_block(
            Bucket=BUCKET_NAME,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': False,
                'IgnorePublicAcls': False,
                'BlockPublicPolicy': False,
                'RestrictPublicBuckets': False,
            },
        )

        # Bucket policy for public read
        bucket_policy = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': 'Allow',
                    'Principal': '*',
                    'Action': 's3:GetObject',
                    'Resource': f'arn:aws:s3:::{BUCKET_NAME}/*',
                },
            ],
        }
        s3.put_bucket_policy(
            Bucket=BUCKET_NAME,
            Policy=json.dumps(bucket_policy),
        )

        # Static website hosting
        s3.put_bucket_website(
            Bucket=BUCKET_NAME,
            WebsiteConfiguration={
                'IndexDocument': {'Suffix': 'index.html'},
                'ErrorDocument': {'Key': 'index.html'},  # SPA fallback
            },
        )

        print('   ✅ Public access configured.')
    except ClientError as e:
        print(f'   ⚠️  Could not configure public access: {e}')
        print('   You may need to configure this manually in Yandex Cloud console.')
        print('   Or ensure the service account has the "storage.admin" role.')

    # Print summary
    print(f'\n📊 Summary: {uploaded} uploaded, {skipped} failed')
    if uploaded > 0:
        website_url = f'https://{BUCKET_NAME}.storage.yandexcloud.net'
        print(f'\n🌐 Website URL: {website_url}')
        print(f'   (or configured custom domain)')


def main() -> None:
    """Build and deploy the frontend to Yandex Object Storage."""
    print('=' * 60)
    print('🚀 Deploy VK Admin Panel Frontend')
    print('=' * 60)
    print()

    _check_prerequisites()
    _build_frontend()
    _upload_to_s3()

    print('\n✅ Deployment complete!')


if __name__ == '__main__':
    main()
