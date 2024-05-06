import os
from typing import TYPE_CHECKING
from uuid import uuid4

import boto3
import pytest
import requests
from logzero import logger
from simplesingletable import DynamoDbMemory
from simplesingletable.utils import truncate_dynamo_table

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table


@pytest.fixture()
def dynamodb_memory(local_dynamodb_test_table, dynamodb_via_docker) -> DynamoDbMemory:
    reset_local_dynamodb_test_table(local_dynamodb_test_table)
    yield DynamoDbMemory(
        logger=logger,
        table_name=local_dynamodb_test_table.table_name,
        endpoint_url=dynamodb_via_docker,
        connection_params={
            "aws_access_key_id": "unused",
            "aws_secret_access_key": "unused",
            "region_name": "us-west-2",
        },
    )


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "src", "tests", "docker-compose.yml")


def is_responsive(url):
    try:
        response = requests.get(url)
        if response.status_code == 400:
            return True
    except requests.ConnectionError:
        return False


@pytest.fixture(scope="session")
def dynamodb_via_docker(docker_ip, docker_services):
    # `port_for` takes a container port and returns the corresponding host port
    port = docker_services.port_for("dynamodb", 8000)
    url = "http://{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(timeout=30.0, pause=0.1, check=lambda: is_responsive(url))
    return url


@pytest.fixture(scope="session")
def local_dynamodb_test_table(dynamodb_via_docker) -> "Table":
    table_created = False
    table_name = f"delta-dynamodb-test-table-{uuid4().hex}"

    aws_access_key_id = "unused"
    aws_secret_access_key = "unused"
    region_name = "us-west-2"

    client = boto3.client(
        "dynamodb",
        endpoint_url=dynamodb_via_docker,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name,
    )
    resource = boto3.resource(
        "dynamodb",
        endpoint_url=dynamodb_via_docker,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name,
    )

    create_table_kwargs = {
        "TableName": table_name,
        "KeySchema": [
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "gsitype", "AttributeType": "S"},
            {"AttributeName": "gsitypesk", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "gsi2pk", "AttributeType": "S"},
            {"AttributeName": "gsi3pk", "AttributeType": "S"},
            {"AttributeName": "gsi3sk", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "gsitype",
                "KeySchema": [
                    {"AttributeName": "gsitype", "KeyType": "HASH"},
                    {"AttributeName": "gsitypesk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "gsi1",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "pk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "gsi2",
                "KeySchema": [
                    {"AttributeName": "gsi2pk", "KeyType": "HASH"},
                    {"AttributeName": "pk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "gsi3",
                "KeySchema": [
                    {"AttributeName": "gsi3pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi3sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        "BillingMode": "PAY_PER_REQUEST",
    }
    try:
        resp = client.create_table(**create_table_kwargs)
        dynamodb_table_arn = resp["TableDescription"]["TableArn"]
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=table_name)
        logger.info(f"Dynamo Table Created {table_name=} {dynamodb_table_arn=}")
        table_created = True
        yield resource.Table(table_name)
    finally:
        if table_created:
            logger.info(f"Deleting generated dynamo table {table_name=}")
            client.delete_table(TableName=table_name)


def reset_local_dynamodb_test_table(table: "Table"):
    logger.debug(f"Resetting table {table.table_name}")
    truncate_dynamo_table(table)
