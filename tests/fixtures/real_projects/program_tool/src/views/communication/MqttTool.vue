<template>
  <section class="mqtt-tool">
    <h1>MQTT test tool</h1>
    <input v-model="brokerUrl" placeholder="ws://broker.emqx.io:8083/mqtt" />
    <input v-model="publishTopic" placeholder="topic to publish" />
    <textarea v-model="payload" placeholder="message payload"></textarea>
    <button @click="connect">connect websocket broker</button>
    <button @click="subscribe">subscribe topic qos</button>
    <button @click="publish">publish topic qos</button>
    <pre>{{ logs.join('\n') }}</pre>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { MqttConnectionInfo, MqttMessage, MqttStats } from '@/types'
import { createMqttTester, formatQoSDescription, validateMqttTopic } from '@/utils/mqttUtils'

const brokerUrl = ref('ws://broker.emqx.io:8083/mqtt')
const publishTopic = ref('demo/topic')
const payload = ref('hello from browser websocket mqtt client')
const logs = ref<string[]>([])
const tester = createMqttTester({ brokerUrl: brokerUrl.value, protocol: 'ws', port: 8083 })

function logConnection(info: MqttConnectionInfo, stats: MqttStats) {
  logs.value.push(`${info.state} ${info.brokerUrl} reconnect=${stats.reconnectCount}`)
}

async function connect() {
  await tester.connect()
  logConnection(tester.getConnectionInfo(), tester.getStats())
}

function subscribe() {
  if (!validateMqttTopic(publishTopic.value)) return
  tester.subscribe(publishTopic.value, 1)
  logs.value.push(`subscribe ${publishTopic.value} ${formatQoSDescription(1)}`)
}

function publish() {
  tester.publishMessage(publishTopic.value, payload.value, 1)
  const messages: MqttMessage[] = tester.getMessages()
  logs.value.push(`publish ${messages.length} messages`)
}
</script>
