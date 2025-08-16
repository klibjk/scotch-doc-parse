import boto3
from functools import lru_cache


@lru_cache(maxsize=1)
def get_boto3_client(service_name: str):
    return boto3.client(service_name)


@lru_cache(maxsize=1)
def get_boto3_resource(service_name: str):
    return boto3.resource(service_name)
