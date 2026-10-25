import { useEffect, useState, FormEvent } from 'react';
import { FaEye, FaEyeSlash } from 'react-icons/fa';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../hooks/useTranslation';
import { useNavigate } from 'react-router-dom';
import { useAppInit } from '../contexts/AppInitContext';
import ThemeChanger from './ThemeChanger';
import LanguageSelector from './LanguageSelector';
import Logo from './Logo';
import { clearSignoutReason, readSignoutReason } from '@/api/signoutReason';

/** A keyboard that pops up on its own covers half a phone screen; a mouse user loses nothing. */
const hasFinePointer = () =>
  typeof window !== 'undefined' && window.matchMedia('(pointer: fine)').matches;

export default function LoginView() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Why the panel came back here, when it was not the user's own doing: the
  // screen they were on has gone, and a login form with no explanation reads
  // as a glitch.
  const [signoutReason] = useState(readSignoutReason);
  useEffect(() => clearSignoutReason(), []);
  const { login } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await login(username, password);
      navigate('/');
    } catch (err) {
      setError(t('login.invalid'));
    }
  };

  return (
    // Phone: the form is the page, edge to edge — a card with a sliver of
    // background around it only wastes the width. From sm up it is a card
    // on the same tinted field the rest of the app sits on.
    <div className="min-h-dvh flex flex-col sm:items-center sm:justify-center stg-backdrop sm:p-6">
      {/* The header that normally carries these only exists after login,
          same as in the onboarding wizard. */}
      <div className="fixed top-2 right-2 z-10 flex items-center gap-1">
        <ThemeChanger />
        <LanguageSelector />
      </div>

      <main className="flex-1 sm:flex-none flex flex-col justify-center w-full sm:max-w-sm bg-base-100 px-6 pt-20 pb-12 sm:p-8 sm:rounded-2xl sm:border sm:border-base-content/10 sm:shadow-xl">
        <div className="flex flex-col items-center text-center">
          <div className="w-28">
            <Logo />
          </div>
          <h2 className="mt-6 text-center text-3xl font-extrabold">
            <p>{t('login.title')}</p><p>boneIO Black</p>
          </h2>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="rounded-md shadow-xs -space-y-px">
            <div className='my-4'>
              <label htmlFor="username" className="sr-only">
                {t('login.username')}
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                className="input  w-full"
                placeholder={t('login.username')}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="mt-4">
              <label htmlFor="password" className="sr-only">
                {t('login.password')}
              </label>
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                required
                className="input  w-full"
                placeholder={t('login.password')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="btn btn-ghost btn-square btn-sm h-10 w-10"
                aria-label={showPassword ? t('login.hide_password') : t('login.show_password')}
                aria-pressed={showPassword}
                title={showPassword ? t('login.hide_password') : t('login.show_password')}
              >
                {showPassword ? <FaEyeSlash className="h-5 w-5 opacity-70" /> : <FaEye className="h-5 w-5 opacity-70" />}
              </button>
            </div>
          </div>

          {error && (
            <div role="alert" className="alert alert-error alert-soft text-sm">
              {error}
            </div>
          )}

          <div>
            <button type="submit" className="btn btn-primary w-full">
              {t('login.submit')}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
