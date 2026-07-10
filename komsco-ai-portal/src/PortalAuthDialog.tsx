import React from 'react';
import { KeyRound, X } from 'lucide-react';
import { connectOpenShiftToken } from './api';
import './portalAuth.css';

export const PortalAuthDialog: React.FC<{ onConnected: () => Promise<void> }> = ({ onConnected }) => {
  const [open, setOpen] = React.useState(false);
  const [token, setToken] = React.useState('');
  const [error, setError] = React.useState('');
  const [connecting, setConnecting] = React.useState(false);

  const connect = async (event: React.FormEvent) => {
    event.preventDefault();
    setConnecting(true);
    setError('');
    try {
      await connectOpenShiftToken(token);
      await onConnected();
      setToken('');
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'OpenShift 인증에 실패했습니다.');
    } finally {
      setConnecting(false);
    }
  };

  return (
    <>
      <button className="portal-auth-trigger" onClick={() => setOpen(true)} type="button">
        <KeyRound aria-hidden="true" />
        토큰 연결
      </button>
      {open && (
        <div className="portal-auth-backdrop" role="presentation">
          <section aria-labelledby="portal-auth-title" aria-modal="true" className="portal-auth-dialog" role="dialog">
            <header>
              <div>
                <span>OpenShift 연결</span>
                <h2 id="portal-auth-title">사용자 토큰 입력</h2>
              </div>
              <button aria-label="닫기" className="portal-auth-close" onClick={() => setOpen(false)} type="button">
                <X aria-hidden="true" />
              </button>
            </header>
            <p>
              이 토큰으로 사용자의 OpenShift 권한을 확인합니다. 권한 밖의 클러스터 정보는 조회되지 않습니다.
            </p>
            <form onSubmit={connect}>
              <label htmlFor="portal-openshift-token">OpenShift API 토큰</label>
              <input
                autoComplete="off"
                autoFocus
                id="portal-openshift-token"
                onChange={(event) => setToken(event.target.value)}
                placeholder="sha256~..."
                spellCheck={false}
                type="password"
                value={token}
              />
              <small>
                웹 콘솔의 사용자 메뉴에서 <strong>로그인 명령 복사</strong>를 열거나, 로그인된 터미널에서{' '}
                <code>oc whoami -t</code>로 확인할 수 있습니다.
              </small>
              {error && <div className="portal-auth-error" role="alert">{error}</div>}
              <footer>
                <button className="portal-auth-cancel" onClick={() => setOpen(false)} type="button">취소</button>
                <button className="portal-auth-submit" disabled={connecting || !token.trim()} type="submit">
                  {connecting ? '확인 중' : '연결'}
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}
    </>
  );
};
