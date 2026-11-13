import React, { useEffect, useRef, useState } from "react";
import { useAppConfig } from "./hooks/useAppConfig";
import { useAuthStatus } from "./hooks/useAuthStatus";

/**
 * If unauthenticated, it shows the AuthModal as an overlay, but still renders the app behind it.
 * 
 * If authenticated, it silently primes the Coder OIDC session by loading
 * the OIDC callback endpoint in a hidden iframe. This is a workaround:
 * without this, users would see the Coder login screen when opening an embedded terminal.
 * 
 * The iframe is removed as soon as it loads, or after a fallback timeout.
 */
export default function AuthGate() {
  const [coderAuthDone, setCoderAuthDone] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const { config, isLoadingConfig, configError } = useAppConfig(); // Use the hook
  const { isAuthenticated, isLoading: isLoadingAuth } = useAuthStatus();

  useEffect(() => {
    if (isAuthenticated && !isLoadingAuth && !coderAuthDone && config && !isLoadingConfig && !configError) {
      console.debug('[pad.ws] Priming Coder OIDC session');
      const setupIframe = async () => {
        try {
          if (!config.coderUrl) {
            console.warn('[pad.ws] Coder URL not found in config, skipping OIDC priming');
            setCoderAuthDone(true);
            return;
          }
          
          const iframe = document.createElement("iframe");
          iframe.style.display = "none";
          iframe.src = `${config.coderUrl}/api/v2/users/oidc/callback?redirect=%2F`;
          console.debug(`[pad.ws] (Silently) Priming Coder OIDC session for ${config.coderUrl}`);

          // Do not remove the iframe on the first onload: the Coder callback
          // redirects through Keycloak, and removing it early aborts the OIDC
          // flow. Keep it until the flow has had time to complete.
          const cleanup = () => {
            if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
            setCoderAuthDone(true);
          };

          document.body.appendChild(iframe);
          iframeRef.current = iframe;

          // The callback may redirect through Keycloak and back. 15s is enough
          // for the SSO round trip without leaving a hidden frame around.
          timeoutRef.current = window.setTimeout(cleanup, 15000);
        } catch (error) {
          console.error('[pad.ws] Error setting up Coder OIDC priming:', error);
          setCoderAuthDone(true);
        }
      };
      
      setupIframe();
      
      // Cleanup on unmount or re-run
      return () => {
        if (iframeRef.current && iframeRef.current.parentNode) {
          iframeRef.current.parentNode.removeChild(iframeRef.current);
        }
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }
      };
    } else if (configError) {
      console.error('[pad.ws] Failed to load app config for OIDC priming:', configError);
      setCoderAuthDone(true); // Mark as done to prevent retries if config fails
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, isLoadingAuth, coderAuthDone, config, isLoadingConfig, configError]);

  return null;
}
