from unittest import TestCase

from mock import Mock

from pact.message_consumer_v3 import MessageConsumerV3
from pact.provider import Provider
from pact.message_pact_v3 import MessagePactV3


class MessageConsumerV3TestCase(TestCase):
    def setUp(self):
        self.mock_service = Mock(MessagePactV3)
        self.provider = Mock(Provider)
        self.message_consumer = MessageConsumerV3('TestMessageConsumerV3', service_cls=self.mock_service)

    def test_init(self):
        result = MessageConsumerV3('TestMessageConsumerV3')
        self.assertIsInstance(result, MessageConsumerV3)
        self.assertEqual(result.name, 'TestMessageConsumerV3')
        self.assertIs(result.service_cls, MessagePactV3)

    def test_has_pact_with(self):
        result = self.message_consumer.has_pact_with(self.provider)
        self.assertIs(result, self.mock_service.return_value)
        self.mock_service.assert_called_once_with(
            consumer=self.message_consumer, provider=self.provider,
            pact_dir=None, version='3.0.0',
            broker_base_url=None, publish_to_broker=False,
            broker_username=None, broker_password=None,
            broker_token=None, file_write_mode='merge')

    def test_has_pact_with_customer_all_options(self):
        result = self.message_consumer.has_pact_with(
            self.provider, pact_dir='/pacts', version='3.0.0',
            file_write_mode='merge')

        self.assertIs(result, self.mock_service.return_value)
        self.mock_service.assert_called_once_with(
            consumer=self.message_consumer, provider=self.provider,
            pact_dir='/pacts', version='3.0.0',
            broker_base_url=None, publish_to_broker=False,
            broker_username=None, broker_password=None, broker_token=None,
            file_write_mode='merge')

    def test_has_pact_with_not_a_provider(self):
        with self.assertRaises(ValueError):
            self.message_consumer.has_pact_with(None)
