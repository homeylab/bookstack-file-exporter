import os

class CredentialsMissingException(Exception):
    """ Use this exception when credentials have not been provided from env variables """
    def __init__(self, token_field: str, token_key: str):
        self.message: str = f"Credentials not found, set credentials using env vars: {token_field} and {token_key}"
        super().__init__(self.message)

def ensure_credentials(token_id_env, token_key_env):
    if (not token_id_env in os.environ) or (not token_key_env in os.environ):
        raise CredentialsMissingException(token_id_env, token_key_env)