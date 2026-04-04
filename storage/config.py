from dataclasses import dataclass

@dataclass(frozen=True)
class PostgreConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    # pool
    min_size: int = 1
    max_size: int = 10
    timeout: float = 30.0
    max_idle: float = 300.0
    
    