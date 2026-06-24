<template>
  <ToolPanel title="JSON to entity" description="Generate Java TypeScript CSharp Python class or interface code">
    <select v-model="language">
      <option value="java">Java</option>
      <option value="typescript">TypeScript</option>
      <option value="csharp">CSharp</option>
      <option value="python">Python</option>
    </select>
    <textarea v-model="jsonInput" placeholder="JSON input"></textarea>
    <button @click="convertToEntity">generate entity class interface</button>
    <CodeEditor v-model="entityOutput" :language="language" title="entity output" />
  </ToolPanel>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CodeEditor from '@/components/CodeEditor.vue'
import ToolPanel from '@/components/ToolPanel.vue'
import { jsonToCSharp, jsonToJava, jsonToPython, jsonToTypeScript } from '@/utils/jsonToEntity'

const language = ref<'java' | 'typescript' | 'csharp' | 'python'>('java')
const jsonInput = ref('{"id":1,"name":"demo","items":[{"price":9.9}]}')
const entityOutput = ref('')

function convertToEntity() {
  const className = 'Entity'
  if (language.value === 'java') entityOutput.value = jsonToJava(jsonInput.value, className)
  if (language.value === 'typescript') entityOutput.value = jsonToTypeScript(jsonInput.value, className)
  if (language.value === 'csharp') entityOutput.value = jsonToCSharp(jsonInput.value, className)
  if (language.value === 'python') entityOutput.value = jsonToPython(jsonInput.value, className)
}
</script>
