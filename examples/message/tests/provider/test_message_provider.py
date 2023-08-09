from collections import OrderedDict
import pytest
from pact import MessageProvider

PACT_BROKER_URL = "http://localhost"
PACT_BROKER_USERNAME = "pactbroker"
PACT_BROKER_PASSWORD = "pactbroker"
PACT_DIR = "pacts"


@pytest.fixture
def default_opts():
    return {
        'broker_username': PACT_BROKER_USERNAME,
        'broker_password': PACT_BROKER_PASSWORD,
        'verbose': True,
        'publish_version': '3',
        'publish_verification_results': True
    }


def document_created_handler():
    return {
        "event": "ObjectCreated:Put",
        "documentName": "document.doc",
        "creator": "PF",
        "documentType": "microsoft-word"
    }


def document_deleted_handler():
    return {
        "event": "ObjectCreated:Delete",
        "documentName": "document.doc",
        "creator": "TP",
        "documentType": "microsoft-word"
    }


def test_verify_success():
    provider = MessageProvider(
        message_providers={
            'A document created successfully': document_created_handler,
            'A document deleted successfully': document_deleted_handler
        },
        provider='ContentProvider',
        consumer='DetectContentLambda',
        pact_dir='pacts'

    )
    with provider:
        provider.verify()

def test_verify_failure_when_a_provider_missing():
    provider = MessageProvider(
        message_providers={
            'A document created successfully': document_created_handler,
        },
        provider='ContentProvider',
        consumer='DetectContentLambda',
        pact_dir='pacts'

    )

    with pytest.raises(AssertionError):
        with provider:
            provider.verify()

def test_verify_from_pact_url(default_opts):
    provider = MessageProvider(
        message_providers={
            'A document created successfully': document_created_handler,
            'A document deleted successfully': document_deleted_handler
        },
        provider='ContentProvider',
        consumer='DetectContentLambda',
    )

    with provider:
        provider.verify(
            "http://localhost/pacts/provider/ContentProvider/consumer/DetectContentLambda/latest",
            **default_opts
        )

def test_verify_from_broker(default_opts):
    provider = MessageProvider(
        message_providers={
            'A document created successfully': document_created_handler,
            'A document deleted successfully': document_deleted_handler
        },
        provider='ContentProvider',
        consumer='DetectContentLambda',

    )

    with provider:
        provider.verify_with_broker(broker_url=PACT_BROKER_URL,
                                                     **default_opts,
                                                     enable_pending=True,
                                                     include_wip_pacts_since='2018-01-01',
                                                     consumer_version_selectors=[
                                                         OrderedDict([("mainBranch", True)]),
                                                         OrderedDict([("deployedOrReleased", True)]
                                                                     ),
                                                     ],
                                                     )