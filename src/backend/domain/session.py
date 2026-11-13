from typing import Optional, Dict, Any, Tuple
import asyncio
import json
import time
import jwt
from jwt.jwks_client import PyJWKClient
import httpx
from redis.asyncio import Redis as AsyncRedis

OIDC_STATE_TTL = 600  # 10 minutes for login transaction
SESSION_LOCK_TTL = 10  # seconds for refresh serialization lock

class Session:
    """Domain class for managing user sessions"""
    
    def __init__(self, redis_client: AsyncRedis, oidc_config: Dict[str, str]):
        """
        Initialize a new Session instance.
        
        Args:
            redis_client: The Redis client to use for session storage
            oidc_config: Configuration for the OIDC provider
        """
        self.redis_client = redis_client
        self.oidc_config = oidc_config
        self._jwks_client = None

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session data from Redis.
        
        Args:
            session_id: The session ID to retrieve
            
        Returns:
            The session data or None if not found
        """
        try:
            session_data = await self.redis_client.get(f"session:{session_id}")
            if session_data:
                return json.loads(session_data)
        except json.JSONDecodeError as e:
            print(f"Error decoding session data for {session_id}: {str(e)}")
        except Exception as e:
            print(f"Error retrieving session {session_id}: {str(e)}")
        return None

    async def set(self, session_id: str, data: Dict[str, Any], expiry: int) -> bool:
        """
        Store session data in Redis with expiry in seconds.
        
        Args:
            session_id: The session ID to store
            data: The session data to store
            expiry: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.redis_client.setex(
                f"session:{session_id}", 
                expiry,
                json.dumps(data)
            )
            return True
        except Exception as e:
            print(f"Error storing session {session_id}: {str(e)}")
            return False

    async def delete(self, session_id: str) -> bool:
        """
        Delete session data from Redis.
        
        Args:
            session_id: The session ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.redis_client.delete(f"session:{session_id}")
            return True
        except Exception as e:
            print(f"Error deleting session {session_id}: {str(e)}")
            return False

    def _server_url(self) -> str:
        """Public OIDC server URL used for browser redirects and issuer validation."""
        return self.oidc_config['server_url']

    def _internal_url(self) -> str:
        """Internal OIDC URL used for token exchange and JWKS fetch."""
        return self.oidc_config.get('internal_url') or self.oidc_config['server_url']

    def get_issuer(self) -> str:
        """Expected JWT issuer for this realm."""
        return f"{self._server_url()}/realms/{self.oidc_config['realm']}"

    def get_auth_url(self) -> str:
        """
        Generate the authentication URL for OIDC login.
        
        Returns:
            The authentication URL
        """
        auth_url = f"{self._server_url()}/realms/{self.oidc_config['realm']}/protocol/openid-connect/auth"
        params = {
            'client_id': self.oidc_config['client_id'],
            'response_type': 'code',
            'redirect_uri': self.oidc_config['redirect_uri'],
            'scope': 'openid profile email'
        }
        return f"{auth_url}?{'&'.join(f'{k}={v}' for k,v in params.items())}"

    def get_token_url(self) -> str:
        """
        Get the token endpoint URL.
        
        Returns:
            The token endpoint URL
        """
        return f"{self._internal_url()}/realms/{self.oidc_config['realm']}/protocol/openid-connect/token"

    def is_token_expired(self, token_data: Dict[str, Any], buffer_seconds: int = 30) -> bool:
        """
        Check if the access token is expired.
        
        Args:
            token_data: The token data to check
            buffer_seconds: Buffer time in seconds before actual expiration
            
        Returns:
            True if the token is expired, False otherwise
        """
        if not token_data or 'access_token' not in token_data:
            return True
            
        try:
            # Get the signing key
            jwks_client = self._get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token_data['access_token'])
            
            # Decode with verification
            decoded = jwt.decode(
                token_data['access_token'],
                signing_key.key,
                algorithms=["RS256"],
                audience=self.oidc_config['client_id'],
            )
            
            # Check expiration
            exp_time = decoded.get('exp', 0)
            current_time = time.time()
            return current_time + buffer_seconds >= exp_time
        except jwt.ExpiredSignatureError:
            return True
        except Exception as e:
            print(f"Error checking token expiration: {str(e)}")
            return True

    def _refresh_lock_key(self, session_id: str) -> str:
        return f"session_lock:{session_id}"

    async def acquire_refresh_lock(self, session_id: str) -> bool:
        """Try to acquire a per-session refresh lock (SET NX EX)."""
        try:
            result = await self.redis_client.set(
                self._refresh_lock_key(session_id),
                "1",
                nx=True,
                ex=SESSION_LOCK_TTL
            )
            return result is not None
        except Exception as e:
            print(f"Error acquiring refresh lock: {str(e)}")
            return False

    async def release_refresh_lock(self, session_id: str) -> None:
        """Release the per-session refresh lock."""
        try:
            await self.redis_client.delete(self._refresh_lock_key(session_id))
        except Exception as e:
            print(f"Error releasing refresh lock: {str(e)}")

    async def refresh_token(self, session_id: str, token_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Refresh the access token using the refresh token.
        
        Args:
            session_id: The session ID
            token_data: The current token data containing the refresh token
            
        Returns:
            Tuple of (success, token_data)
        """
        if not token_data or 'refresh_token' not in token_data:
            return False, token_data
            
        try:
            async with httpx.AsyncClient() as client:
                refresh_response = await client.post(
                    self.get_token_url(),
                    data={
                        'grant_type': 'refresh_token',
                        'client_id': self.oidc_config['client_id'],
                        'client_secret': self.oidc_config['client_secret'],
                        'refresh_token': token_data['refresh_token']
                    }
                )
                
                if refresh_response.status_code != 200:
                    print(f"Token refresh failed: {refresh_response.text}")
                    return False, token_data
                    
                # Get new token data
                new_token_data = refresh_response.json()
                
                # Update session with new tokens
                expiry = new_token_data['refresh_expires_in']
                success = await self.set(session_id, new_token_data, expiry)
                if not success:
                    return False, token_data
                
                return True, new_token_data
        except Exception as e:
            print(f"Error refreshing token: {str(e)}")
            return False, token_data

    async def refresh_token_with_lock(self, session_id: str, token_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Serialize token refresh for a session. If this caller wins the lock, it
        performs the refresh. If another caller holds the lock, we poll the
        stored session up to SESSION_LOCK_TTL seconds and return the refreshed
        data without consuming another refresh token.
        """
        if not token_data or 'refresh_token' not in token_data:
            return False, token_data

        lock_acquired = await self.acquire_refresh_lock(session_id)
        if lock_acquired:
            try:
                # Re-read session under the lock in case another worker refreshed
                # between our read and lock acquisition.
                current_data = await self.get(session_id)
                if current_data and not self.is_token_expired(current_data):
                    return True, current_data
                if current_data:
                    token_data = current_data
                return await self.refresh_token(session_id, token_data)
            finally:
                await self.release_refresh_lock(session_id)

        # Another request is refreshing; wait for it to finish and re-read.
        waited = 0.0
        while waited < SESSION_LOCK_TTL:
            await asyncio.sleep(0.1)
            waited += 0.1
            current_data = await self.get(session_id)
            if current_data and not self.is_token_expired(current_data):
                return True, current_data

        return False, token_data

    def _get_jwks_client(self) -> PyJWKClient:
        """
        Get or create a PyJWKClient for token verification.
        
        Returns:
            The JWKs client
        """
        if self._jwks_client is None:
            jwks_url = f"{self._internal_url()}/realms/{self.oidc_config['realm']}/protocol/openid-connect/certs"
            self._jwks_client = PyJWKClient(jwks_url)
        return self._jwks_client

    async def track_event(self, session_id: str, event_type: str, metadata: Dict[str, Any] = None) -> bool:
        """
        Track a session event (login, logout, etc.).
        
        Args:
            session_id: The session ID
            event_type: The type of event
            metadata: Additional metadata for the event
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session_data = await self.get(session_id)
            if session_data:
                if 'events' not in session_data:
                    session_data['events'] = []
                
                event = {
                    'type': event_type,
                    'timestamp': time.time(),
                    'metadata': metadata or {}
                }
                session_data['events'].append(event)
                
                # Update session with new event, preserving the refresh lifetime.
                ttl = session_data.get('refresh_expires_in') or session_data.get('expires_in', 3600)
                return await self.set(session_id, session_data, ttl)
            return False
        except Exception as e:
            print(f"Error tracking event {event_type} for session {session_id}: {str(e)}")
            return False 