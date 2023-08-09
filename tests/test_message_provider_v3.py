import os
# import pytest
from mock import patch, Mock
from unittest import TestCase

from pact.message_provider_v3 import MessageProviderV3
from pact import message_provider_v3


class MessageProviderV3TestCase(TestCase):
    def _mock_response(
            self,
            status=200,
            content="fake response",
            raise_for_status=None):

        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        if raise_for_status:
            mock_resp.raise_for_status.side_effect = raise_for_status

        mock_resp.status_code = status
        mock_resp.text = content
        return mock_resp

    def message_handler(self):
        return {'success': True}

    def setUp(self):
        self.provider = MessageProviderV3(
            provider='DocumentService',
            consumer='DetectContentLambda',
            message_providers={
                'a document created successfully': self.message_handler
            }
        )
        self.options = {
            'broker_username': "test",
            'broker_password': "test",
            'broker_url': "http://localhost",
            'publish_version': '3',
            'publish_verification_results': False
        }

    def test_init(self):
        self.assertIsInstance(self.provider, MessageProviderV3)
        self.assertEqual(self.provider.provider, 'DocumentService')
        self.assertEqual(self.provider.consumer, 'DetectContentLambda')
        self.assertEqual(self.provider.pact_dir, os.getcwd())
        self.assertEqual(self.provider.version, '3.0.0')
        self.assertEqual(self.provider.proxy_host, '127.0.0.1')
        self.assertEqual(self.provider.proxy_port, '1234')

    @patch('pact.verifier_v3.VerifierV3.verify_pacts', return_value=(0, 'logs'))
    def test_verify(self, mock_verify_pacts):
        self.provider.verify()

        assert mock_verify_pacts.call_count == 1
        mock_verify_pacts.assert_called_with(sources=[f'{self.provider.pact_dir}/{self.provider._pact_file()}'],
                                             )

    @patch('pact.verifier_v3.VerifierV3.verify_pacts', return_value=(0, 'logs'))
    def test_verify_with_broker(self, mock_verify_pacts):
        self.provider.verify_with_broker(**self.options)

        assert mock_verify_pacts.call_count == 1
        mock_verify_pacts.assert_called_with(
            enable_pending=False,
            include_wip_pacts_since=None,
            broker_username="test",
            broker_password="test",
            broker_url="http://localhost",
            publish_version='3',
            publish_verification_results=False
        )


class MessageProviderV3ContextManagerTestCase(MessageProviderV3TestCase):
    def setUp(self):
        super(MessageProviderV3ContextManagerTestCase, self).setUp()

    @patch('pact.MessageProviderV3._start_proxy', return_value=0)
    @patch('pact.MessageProviderV3._stop_proxy', return_value=0)
    def test_successful(self, mock_stop_proxy, mock_start_proxy):
        with self.provider:
            pass

        mock_start_proxy.assert_called_once()
        mock_stop_proxy.assert_called_once()

    @patch('pact.MessageProviderV3._wait_for_server_start', side_effect=RuntimeError('boom!'))
    @patch('pact.MessageProviderV3._start_proxy', return_value=0)
    @patch('pact.MessageProviderV3._stop_proxy', return_value=0)
    def test_stop_proxy_on_runtime_error(self, mock_stop_proxy, mock_start_proxy, mock_wait_for_server_start,):
        with self.provider:
            pass

        mock_start_proxy.assert_called_once()
        mock_stop_proxy.assert_called_once()


class StartProxyTestCase(MessageProviderV3TestCase):
    def setUp(self):
        super(StartProxyTestCase, self).setUp()


class StopProxyTestCase(MessageProviderV3TestCase):
    def setUp(self):
        super(StopProxyTestCase, self).setUp()

    @patch('requests.post')
    def test_shutdown_successfully(self, mock_requests):
        mock_requests.return_value = self._mock_response(content="success")
        self.provider._stop_proxy()


class SetupStateTestCase(MessageProviderV3TestCase):
    def setUp(self):
        super(SetupStateTestCase, self).setUp()

    @patch('requests.post')
    def test_shutdown_successfully(self, mock_requests):
        mock_requests.return_value = self._mock_response(status=201)
        self.provider._setup_states()
        expected_payload = {
            'messageHandlers': {
                'a document created successfully': self.message_handler()
            }
        }

        mock_requests.assert_called_once_with(f'{self.provider._proxy_url()}/setup', verify=False, json=expected_payload)


class WaitForServerStartTestCase(MessageProviderV3TestCase):
    def setUp(self):
        super(WaitForServerStartTestCase, self).setUp()

    @patch.object(message_provider_v3.requests, 'Session')
    @patch.object(message_provider_v3, 'Retry')
    @patch.object(message_provider_v3, 'HTTPAdapter')
    @patch('pact.MessageProviderV3._stop_proxy')
    def test_wait_for_server_start_success(self, mock_stop_proxy, mock_HTTPAdapter, mock_Retry, mock_Session):
        mock_Session.return_value.get.return_value.status_code = 200
        self.provider._wait_for_server_start()

        session = mock_Session.return_value
        session.mount.assert_called_once_with(
            'http://', mock_HTTPAdapter.return_value)
        session.get.assert_called_once_with(f'{self.provider._proxy_url()}/ping', verify=False)
        mock_HTTPAdapter.assert_called_once_with(
            max_retries=mock_Retry.return_value)
        mock_Retry.assert_called_once_with(total=9, backoff_factor=0.5)
        mock_stop_proxy.assert_not_called()

    @patch.object(message_provider_v3.requests, 'Session')
    @patch.object(message_provider_v3, 'Retry')
    @patch.object(message_provider_v3, 'HTTPAdapter')
    @patch('pact.MessageProviderV3._stop_proxy')
    def test_wait_for_server_start_failure(self, mock_stop_proxy, mock_HTTPAdapter, mock_Retry, mock_Session):
        mock_Session.return_value.get.return_value.status_code = 500

        with self.assertRaises(RuntimeError):
            self.provider._wait_for_server_start()

        session = mock_Session.return_value
        session.mount.assert_called_once_with(
            'http://', mock_HTTPAdapter.return_value)
        session.get.assert_called_once_with(f'{self.provider._proxy_url()}/ping', verify=False)
        mock_HTTPAdapter.assert_called_once_with(
            max_retries=mock_Retry.return_value)
        mock_Retry.assert_called_once_with(total=9, backoff_factor=0.5)
        mock_stop_proxy.assert_called_once()
