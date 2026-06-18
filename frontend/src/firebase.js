// Firebase initialization for CloudProof.
// Config values come from environment variables (see frontend/.env).
// Get them from: Firebase Console → Project settings → General → Your apps → Web app.
import { initializeApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  setPersistence,
  browserLocalPersistence,
} from 'firebase/auth';

const firebaseConfig = {
  apiKey:            process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain:        process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId:         process.env.REACT_APP_FIREBASE_PROJECT_ID,
  storageBucket:     process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
  appId:             process.env.REACT_APP_FIREBASE_APP_ID,
};

// Helpful guard so a missing .env produces a clear message instead of a cryptic crash.
export const firebaseConfigured = Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);

const app  = initializeApp(firebaseConfig);
export const auth = getAuth(app);

// Keep the user signed in across page reloads.
setPersistence(auth, browserLocalPersistence).catch(() => {});

export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: 'select_account' });

export default app;
