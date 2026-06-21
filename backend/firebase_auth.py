"""
Firebase Admin SDK helper.

Verifies Firebase ID tokens sent from the frontend so the backend can trust
the user's identity (and whether their email is verified).

Service-account credentials are loaded from ONE of these env vars:
  FIREBASE_SERVICE_ACCOUNT       — path to the downloaded service-account .json
  FIREBASE_SERVICE_ACCOUNT_JSON  — the service-account JSON as an inline string
Get the file from: Firebase Console → Project settings → Service accounts
→ "Generate new private key".
"""

import os
import json
import logging
import threading

import firebase_admin
from firebase_admin import credentials, auth as fb_auth
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False


def _ensure_initialized():
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        if firebase_admin._apps:  # already initialized elsewhere
            _initialized = True
            return

        cred = None
        inline = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        path   = os.getenv('FIREBASE_SERVICE_ACCOUNT')

        # Resolve relative path against the directory this file lives in
        if path and not os.path.isabs(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)

        if inline:
            cred = credentials.Certificate(json.loads(inline))
        elif path and os.path.exists(path):
            cred = credentials.Certificate(path)
            logger.info(f'Firebase: using service account at {path}')
        else:
            logger.warning(f'Firebase: no service account found at {path!r}, falling back to ADC')
            cred = None

        if cred is not None:
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
        _initialized = True
        logger.info('Firebase Admin SDK initialized.')


def verify_id_token(id_token: str) -> dict:
    """
    Verify a Firebase ID token. Returns the decoded claims dict
    (uid, email, email_verified, name, ...). Raises on invalid token.
    """
    _ensure_initialized()
    return fb_auth.verify_id_token(id_token)
