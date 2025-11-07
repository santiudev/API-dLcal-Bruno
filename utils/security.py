"""
Utilidades de seguridad para la integración con dLocal Go
"""
from typing import Dict


def get_dlocal_headers(api_key: str, secret_key: str) -> Dict[str, str]:
    """
    Genera los headers necesarios para dLocal Go API
    
    dLocal Go usa autenticación Bearer simple con API Key y Secret Key
    
    Args:
        api_key: API Key de dLocal Go
        secret_key: Secret Key de dLocal Go
        
    Returns:
        dict: Headers completos para requests a dLocal Go
    """
    # Bearer token simple: API_KEY:SECRET_KEY
    bearer_token = f"{api_key}:{secret_key}"
    
    return {
        'Authorization': f'Bearer {bearer_token}',
        'Content-Type': 'application/json'
    }

