// "Sign in" is a demo gate only: there is no real authentication (the app is a simulated company). One click, remembered in this browser.
const KEY = 'pg-signed-in'
export const isSignedIn = () => { try { return localStorage.getItem(KEY) === '1' } catch { return false } }
export const signIn = () => { try { localStorage.setItem(KEY, '1') } catch { /* private window: the session just will not persist */ } }
export const signOut = () => { try { localStorage.removeItem(KEY) } catch { /* ignore */ } }
