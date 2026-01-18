import React from 'react'

export default function TestComponent() {
  const test = true
  
  if (test) {
    return (
      <div>Test</div>
    )
  }
  
  return (
    <div>Main</div>
  )
}
