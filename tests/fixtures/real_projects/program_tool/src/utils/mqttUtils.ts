import mqtt, { type IClientOptions, type MqttClient } from 'mqtt'
import type {
  MqttConnectionConfig,
  MqttConnectionInfo,
  MqttMessage,
  MqttStats,
  MqttSubscription,
} from '@/types'

export class MqttTester {
  private client: MqttClient | null = null
  private messages: MqttMessage[] = []
  private subscriptions = new Map<string, MqttSubscription>()
  private stats: MqttStats
  private connectionInfo: MqttConnectionInfo

  constructor(private config: Partial<MqttConnectionConfig> = {}) {
    this.stats = {
      messagesPublished: 0,
      messagesReceived: 0,
      bytesPublished: 0,
      bytesReceived: 0,
      subscriptionCount: 0,
      connectionDuration: 0,
      reconnectCount: 0,
      lastActivity: 0,
    }
    this.connectionInfo = {
      state: 'disconnected',
      brokerUrl: config.brokerUrl ?? 'ws://localhost:8083/mqtt',
      clientId: config.clientId ?? `mqtt-tool-${Date.now()}`,
      protocol: config.protocol ?? 'ws',
      reconnectCount: 0,
    }
  }

  async connect(): Promise<void> {
    const options: IClientOptions = {
      clientId: this.connectionInfo.clientId,
      keepalive: this.config.keepAlive ?? 60,
      reconnectPeriod: this.config.reconnectPeriod ?? 1000,
      connectTimeout: this.config.connectTimeout ?? 5000,
    }
    this.connectionInfo.state = 'connecting'
    this.client = mqtt.connect(this.connectionInfo.brokerUrl, options)
    this.connectionInfo.state = 'connected'
  }

  disconnect(): void {
    this.client?.end(true)
    this.connectionInfo.state = 'disconnected'
  }

  publishMessage(topic: string, payload: string, qos: 0 | 1 | 2 = 0): void {
    this.client?.publish(topic, payload, { qos })
    this.messages.push({
      id: `message-${Date.now()}`,
      type: 'published',
      topic,
      payload,
      qos,
      retain: false,
      timestamp: Date.now(),
      size: payload.length,
    })
    this.stats.messagesPublished++
    this.stats.bytesPublished += payload.length
  }

  subscribe(topic: string, qos: 0 | 1 | 2 = 0): void {
    this.client?.subscribe(topic, { qos })
    this.subscriptions.set(topic, {
      id: `subscription-${topic}`,
      topic,
      qos,
      subscribedAt: Date.now(),
      messageCount: 0,
    })
    this.stats.subscriptionCount = this.subscriptions.size
  }

  getMessages(): MqttMessage[] {
    return [...this.messages]
  }

  getStats(): MqttStats {
    return { ...this.stats }
  }

  getConnectionInfo(): MqttConnectionInfo {
    return { ...this.connectionInfo }
  }
}

export function createMqttTester(config?: Partial<MqttConnectionConfig>): MqttTester {
  return new MqttTester(config)
}

export function validateMqttTopic(topic: string): boolean {
  return Boolean(topic) && !topic.includes('#') && !topic.includes('+')
}

export function formatQoSDescription(qos: 0 | 1 | 2): string {
  return ['at most once', 'at least once', 'exactly once'][qos]
}
