# agent keys are compared as exact strings, so keep this checksummed casing; do not normalize
ERC8004_IDENTITY_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"


def agent_key(chain_id: int | str, token_id: int | str, registry: str = ERC8004_IDENTITY_REGISTRY) -> str:
    return f"eip155:{int(chain_id)}/erc721:{registry}/{int(token_id)}"
