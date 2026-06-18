import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  sendEmailVerification,
  sendPasswordResetEmail,
  updateProfile,
  signOut,
} from 'firebase/auth';
import { auth, googleProvider, firebaseConfigured } from '../firebase';

const API = process.env.REACT_APP_API_URL || '';

// Map Firebase auth error codes → friendly messages.
function friendlyError(err) {
  const code = err?.code || '';
  switch (code) {
    case 'auth/invalid-email':         return 'That email address is not valid.';
    case 'auth/user-disabled':         return 'This account has been disabled.';
    case 'auth/user-not-found':
    case 'auth/wrong-password':
    case 'auth/invalid-credential':    return 'Invalid email or password.';
    case 'auth/email-already-in-use':  return 'That email is already registered. Try signing in.';
    case 'auth/weak-password':         return 'Password should be at least 6 characters.';
    case 'auth/popup-closed-by-user':  return 'Google sign-in was cancelled.';
    case 'auth/too-many-requests':     return 'Too many attempts. Please wait a moment and try again.';
    case 'auth/network-request-failed':return 'Network error. Check your connection.';
    default:                           return err?.message || 'Something went wrong. Please try again.';
  }
}

export default function Auth() {
  const navigate     = useNavigate();
  const [params]     = useSearchParams();
  const [mode, setMode]   = useState('login');  // 'login' | 'signup' | 'forgot'
  const [form, setForm]   = useState({ username: '', name: '', email: '', password: '', confirm: '' });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');
  const [info,    setInfo]    = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [pendingVerify, setPendingVerify] = useState(null); // email awaiting verification

  useEffect(() => {
    const oauthError = params.get('error');
    if (oauthError) setError(decodeURIComponent(oauthError));
  }, [params]);

  const set        = (k, v) => { setForm(f => ({ ...f, [k]: v })); setError(''); };
  const switchMode = (m)    => { setMode(m); setError(''); setInfo(''); setPendingVerify(null); };

  // Persist the app's own JWT (issued by the backend) and route the user.
  const _storeAndRedirect = (data) => {
    localStorage.setItem('cloudproof_token', data.token);
    localStorage.setItem('cloudproof_user',  JSON.stringify(data.user));
    if (!data.user.has_bucket) navigate('/setup');
    else                       navigate(`/${data.user.username}`);
  };

  // Exchange a verified Firebase ID token for a CloudProof session JWT.
  const exchangeFirebaseToken = async (firebaseUser, extra = {}) => {
    const idToken = await firebaseUser.getIdToken(true);
    const { data } = await axios.post(`${API}/api/auth/firebase`, {
      id_token: idToken,
      username: extra.username || '',
      name:     extra.name || firebaseUser.displayName || '',
    });
    return data;
  };

  // ── Login (email + password) ────────────────────────────────────────────────
  const handleLogin = async (e) => {
    e.preventDefault();
    if (!firebaseConfigured) { setError('Firebase is not configured yet. Add your keys to frontend/.env.'); return; }
    setError(''); setInfo(''); setLoading(true);
    try {
      const cred = await signInWithEmailAndPassword(auth, form.email.trim().toLowerCase(), form.password);
      if (!cred.user.emailVerified) {
        await sendEmailVerification(cred.user).catch(() => {});
        await signOut(auth);
        setPendingVerify(cred.user.email);
        return;
      }
      const data = await exchangeFirebaseToken(cred.user);
      _storeAndRedirect(data);
    } catch (err) {
      setError(err.response?.data?.error || friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  // ── Sign up (email + password) ──────────────────────────────────────────────
  const handleSignup = async (e) => {
    e.preventDefault();
    if (!firebaseConfigured) { setError('Firebase is not configured yet. Add your keys to frontend/.env.'); return; }
    if (form.password !== form.confirm) { setError('Passwords do not match.'); return; }
    if (form.password.length < 8)       { setError('Password must be at least 8 characters.'); return; }
    setError(''); setInfo(''); setLoading(true);
    const username = form.username.trim().toLowerCase();
    const email    = form.email.trim().toLowerCase();
    try {
      // 1) Check username/email availability in our DB first.
      await axios.post(`${API}/api/auth/preflight`, { username, email, password: form.password });

      // 2) Create the Firebase identity + send the real verification email.
      const cred = await createUserWithEmailAndPassword(auth, email, form.password);
      if (form.name.trim()) await updateProfile(cred.user, { displayName: form.name.trim() }).catch(() => {});

      // 3) Reserve the username in our DB (row created, email_verified=false for now).
      await exchangeFirebaseToken(cred.user, { username, name: form.name.trim() || username }).catch(() => {});

      // 4) Send verification, sign out, and ask them to verify before first login.
      await sendEmailVerification(cred.user).catch(() => {});
      await signOut(auth);
      setPendingVerify(email);
    } catch (err) {
      setError(err.response?.data?.error || friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  // ── Google sign-in ──────────────────────────────────────────────────────────
  const handleGoogle = async () => {
    if (!firebaseConfigured) { setError('Firebase is not configured yet. Add your keys to frontend/.env.'); return; }
    setError(''); setInfo(''); setLoading(true);
    try {
      const cred = await signInWithPopup(auth, googleProvider);
      const data = await exchangeFirebaseToken(cred.user, { name: cred.user.displayName });
      _storeAndRedirect(data);
    } catch (err) {
      setError(err.response?.data?.error || friendlyError(err));
    } finally {
      setLoading(false);
    }
  };

  // ── Forgot password ─────────────────────────────────────────────────────────
  const handleForgot = async (e) => {
    e.preventDefault();
    if (!firebaseConfigured) { setError('Firebase is not configured yet. Add your keys to frontend/.env.'); return; }
    setError(''); setInfo(''); setLoading(true);
    try {
      await sendPasswordResetEmail(auth, form.email.trim().toLowerCase());
      setInfo('If that email is registered, a password reset link has been sent. Check your inbox.');
    } catch (err) {
      // Don't leak which emails exist — show success-style message anyway for user-not-found.
      if (err?.code === 'auth/user-not-found') {
        setInfo('If that email is registered, a password reset link has been sent. Check your inbox.');
      } else {
        setError(friendlyError(err));
      }
    } finally {
      setLoading(false);
    }
  };

  const GoogleButton = () => (
    <button type="button" className="oauth-btn oauth-google" onClick={handleGoogle} disabled={loading}>
      <svg viewBox="0 0 24 24" height="18">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
      </svg>
      Continue with Google
    </button>
  );

  // ── Verify-email screen ─────────────────────────────────────────────────────
  const renderVerify = () => (
    <div className="auth-verify">
      <div className="auth-verify-icon">📬</div>
      <h2 className="auth-section-title">Verify your email</h2>
      <p className="auth-section-desc">
        We sent a verification link to <strong>{pendingVerify}</strong>.
        Click it to activate your account, then sign in.
      </p>
      <button className="auth-submit" onClick={() => switchMode('login')}>Back to sign in →</button>
      <p className="auth-hint" style={{ marginTop: 14 }}>
        Didn't get it? Check your spam folder. The link expires after a while — sign in to get a fresh one.
      </p>
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="auth-split">

      {/* ── LEFT: the form ─────────────────────────────────────────────────── */}
      <div className="auth-left">
        <div className="auth-left-inner">
          <div className="auth-brand">
            <div className="logo-box">☁</div>
            <span className="auth-brand-name">CloudProof</span>
          </div>

          {pendingVerify ? renderVerify() : (
            <div className="auth-card-flat">
              {mode !== 'forgot' && (
                <>
                  <h1 className="auth-title">
                    {mode === 'login' ? 'Sign in' : 'Create your account'}
                  </h1>
                  <p className="auth-subtitle">
                    {mode === 'login'
                      ? 'Access your CloudProof activity dashboard.'
                      : 'Track and verify your AWS cloud activity.'}
                  </p>

                  <div className="oauth-buttons">
                    <GoogleButton />
                  </div>
                  <div className="auth-divider"><span>or with email</span></div>
                </>
              )}

              {/* ── Forgot password ─────────────────────────────────────────── */}
              {mode === 'forgot' && (
                <>
                  <div className="auth-back" onClick={() => switchMode('login')}>← Back to sign in</div>
                  <h1 className="auth-title">Reset password</h1>
                  <p className="auth-subtitle">Enter your email and we'll send a reset link.</p>
                  <form onSubmit={handleForgot} className="auth-form">
                    <div className="auth-field">
                      <label>Email</label>
                      <input type="email" value={form.email} onChange={e => set('email', e.target.value)}
                        placeholder="you@example.com" required autoFocus />
                    </div>
                    {error && <div className="auth-error">{error}</div>}
                    {info  && <div className="auth-success">{info}</div>}
                    <button type="submit" className="auth-submit" disabled={loading}>
                      {loading ? 'Sending…' : 'Send reset link →'}
                    </button>
                  </form>
                </>
              )}

              {/* ── Login ───────────────────────────────────────────────────── */}
              {mode === 'login' && (
                <form onSubmit={handleLogin} className="auth-form">
                  <div className="auth-field">
                    <label>Email <span className="req">*</span></label>
                    <input type="email" value={form.email} onChange={e => set('email', e.target.value)}
                      placeholder="you@example.com" required autoComplete="email" />
                  </div>
                  <div className="auth-field">
                    <label>Password <span className="req">*</span></label>
                    <div className="auth-pwd-wrap">
                      <input
                        type={showPwd ? 'text' : 'password'}
                        value={form.password} onChange={e => set('password', e.target.value)}
                        placeholder="Your password" required autoComplete="current-password"
                      />
                      <button type="button" className="auth-pwd-toggle" onClick={() => setShowPwd(v => !v)}>
                        {showPwd ? '🙈' : '👁'}
                      </button>
                    </div>
                  </div>
                  <div className="auth-forgot-row">
                    <button type="button" className="auth-link" onClick={() => switchMode('forgot')}>
                      Forgot password?
                    </button>
                  </div>
                  {error && <div className="auth-error">{error}</div>}
                  {info  && <div className="auth-success">{info}</div>}
                  <button type="submit" className="auth-submit" disabled={loading}>
                    {loading ? 'Signing in…' : 'Sign in →'}
                  </button>
                </form>
              )}

              {/* ── Signup ──────────────────────────────────────────────────── */}
              {mode === 'signup' && (
                <form onSubmit={handleSignup} className="auth-form">
                  <div className="auth-field">
                    <label>Username <span className="req">*</span></label>
                    <div className="auth-username-wrap">
                      <span className="auth-host">{window.location.host}/</span>
                      <input
                        type="text" value={form.username}
                        onChange={e => set('username', e.target.value.toLowerCase())}
                        placeholder="your-username" required
                        pattern="[a-z0-9_\-]{3,30}"
                        title="3–30 chars: lowercase letters, numbers, - _"
                      />
                    </div>
                  </div>
                  <div className="auth-field">
                    <label>Display name <span className="auth-optional">(optional)</span></label>
                    <input type="text" value={form.name} onChange={e => set('name', e.target.value)} placeholder="John Doe" />
                  </div>
                  <div className="auth-field">
                    <label>Email <span className="req">*</span></label>
                    <input type="email" value={form.email} onChange={e => set('email', e.target.value)}
                      placeholder="you@example.com" required autoComplete="email" />
                  </div>
                  <div className="auth-field">
                    <label>Password <span className="req">*</span> <span className="auth-optional">(min 8 chars)</span></label>
                    <div className="auth-pwd-wrap">
                      <input
                        type={showPwd ? 'text' : 'password'}
                        value={form.password} onChange={e => set('password', e.target.value)}
                        placeholder="Create a password" required minLength={8} autoComplete="new-password"
                      />
                      <button type="button" className="auth-pwd-toggle" onClick={() => setShowPwd(v => !v)}>
                        {showPwd ? '🙈' : '👁'}
                      </button>
                    </div>
                  </div>
                  <div className="auth-field">
                    <label>Confirm password <span className="req">*</span></label>
                    <input type="password" value={form.confirm} onChange={e => set('confirm', e.target.value)}
                      placeholder="Repeat your password" required autoComplete="new-password" />
                    {form.confirm && form.confirm !== form.password && (
                      <p className="auth-field-err">Passwords don't match.</p>
                    )}
                  </div>
                  {error && <div className="auth-error">{error}</div>}
                  <button type="submit" className="auth-submit" disabled={loading}>
                    {loading ? 'Creating account…' : 'Create account →'}
                  </button>
                </form>
              )}

              {mode !== 'forgot' && (
                <p className="auth-footer">
                  {mode === 'login'
                    ? <>No account? <button className="auth-link" onClick={() => switchMode('signup')}>Create one free</button></>
                    : <>Already have an account? <button className="auth-link" onClick={() => switchMode('login')}>Sign in</button></>}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── RIGHT: what you'll need (AWS requirements) ─────────────────────── */}
      <div className="auth-right">
        <div className="auth-right-inner">
          <h2 className="auth-right-title">What you'll need to connect</h2>
          <p className="auth-right-sub">
            CloudProof reads your CloudTrail logs from S3 to build a verified record of your
            AWS activity. After you sign in, you'll connect your account with:
          </p>

          <ul className="req-list">
            <li className="req-item">
              <div className="req-num">1</div>
              <div className="req-body">
                <div className="req-head">IAM access key &amp; secret</div>
                <div className="req-text">
                  Create an access key under <strong>IAM → Users → Security credentials</strong>.
                  Stored encrypted — used only to read your logs.
                </div>
              </div>
            </li>
            <li className="req-item">
              <div className="req-num">2</div>
              <div className="req-body">
                <div className="req-head">S3 read access</div>
                <div className="req-text">
                  Attach <code>AmazonS3ReadOnlyAccess</code> (or any policy that grants S3 read)
                  to that IAM user.
                </div>
              </div>
            </li>
            <li className="req-item">
              <div className="req-num">3</div>
              <div className="req-body">
                <div className="req-head">CloudTrail → S3</div>
                <div className="req-text">
                  A CloudTrail trail delivering logs to that S3 bucket. We scan the bucket
                  to score your activity.
                </div>
              </div>
            </li>
          </ul>

          <div className="req-note">
            🔒 Read-only. CloudProof never modifies, creates, or deletes anything in your AWS account.
          </div>
        </div>
      </div>
    </div>
  );
}
