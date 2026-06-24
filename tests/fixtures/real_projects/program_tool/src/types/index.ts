export interface ToolItem {
  name: string
  path: string
  description?: string
}

export interface ToolCategory {
  title: string
  tools: ToolItem[]
}

export interface MqttMessage {
  id: string
  type: 'published' | 'received' | 'system' | 'error'
  topic: string
  payload: string
  qos: 0 | 1 | 2
  retain: boolean
  timestamp: number
  size: number
}

export interface MqttSubscription {
  id: string
  topic: string
  qos: 0 | 1 | 2
  subscribedAt: number
  messageCount: number
}

export interface MqttConnectionConfig {
  brokerUrl: string
  port: number
  clientId: string
  keepAlive: number
  reconnectPeriod: number
  connectTimeout: number
  protocol: 'mqtt' | 'mqtts' | 'ws' | 'wss'
}

export interface MqttStats {
  messagesPublished: number
  messagesReceived: number
  bytesPublished: number
  bytesReceived: number
  subscriptionCount: number
  connectionDuration: number
  reconnectCount: number
  lastActivity: number
}

export type MqttConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error'

export interface MqttConnectionInfo {
  state: MqttConnectionState
  brokerUrl: string
  clientId: string
  protocol: string
  lastError?: string
  connectedAt?: number
  reconnectCount: number
}

export interface WatermarkRegion {
  id: string
  x: number
  y: number
  width: number
  height: number
  confidence: number
}

export interface DetectionConfig {
  sensitivity: number
  minRegionSize: number
  maxRegionSize: number
  confidenceThreshold: number
}
