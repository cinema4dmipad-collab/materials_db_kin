from dmr.security.token import HeaderTokenSyncAuth

# Bearer PAT: Authorization: Bearer <token>
API_TOKEN_AUTH = HeaderTokenSyncAuth(
    header_name='Authorization',
    prefix='Bearer',
    security_scheme_name='bearerAuth',
    update_last_used=True,
)
