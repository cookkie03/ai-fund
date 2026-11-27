import * as React from "react"
import { ArrowUpIcon } from "lucide-react"
import { Message, MessageAvatar, MessageContent, MessageGroup, MessageHeader } from "@/ds/ui/message"
import { Bubble, BubbleContent } from "@/ds/ui/bubble"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/ds/ui/input-group"
import { Kbd } from "@/ds/ui/kbd"
import { AgentAvatar, resolveActor } from "@/ds/identity/agent-avatar"

export type ChatMessage = { id: string; actor: string; text: string; time: string }

/** A conversation with an agent or the Bridge: Luca's messages on the right, agents on the left, each signed. */
export function ChatThread({ messages }: { messages: ChatMessage[] }) {
  return (
    <MessageGroup className="gap-4">
      {messages.map((m, i) => {
        const me = resolveActor(m.actor).kind === "human"
        return (
          <Message key={m.id} align={me ? "end" : "start"} className="ds-reveal" style={{ ["--ds-i" as string]: i }}>
            <MessageAvatar><AgentAvatar actor={m.actor} size="sm" /></MessageAvatar>
            <MessageContent>
              <MessageHeader>{resolveActor(m.actor).name} · {m.time}</MessageHeader>
              <Bubble align={me ? "end" : "start"} variant={me ? "default" : "secondary"}><BubbleContent>{m.text}</BubbleContent></Bubble>
            </MessageContent>
          </Message>
        )
      })}
    </MessageGroup>
  )
}

/** The message box: grows to 6 lines, Enter sends, Shift+Enter breaks; Send is the one primary. */
export function Composer({ placeholder = "Message the Portfolio Manager…", disabled, onSend }: { placeholder?: string; disabled?: boolean; onSend?: (text: string) => void }) {
  const [text, setText] = React.useState("")
  const send = () => { if (text.trim()) { onSend?.(text.trim()); setText("") } }
  return (
    <InputGroup>
      <InputGroupTextarea value={text} disabled={disabled} rows={1} className="max-h-36" placeholder={placeholder} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send() } }} />
      <InputGroupAddon align="block-end">
        <span className="text-xs text-muted-foreground"><Kbd>Enter</Kbd> send · <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> new line</span>
        <InputGroupButton variant="default" size="icon-sm" className="ml-auto rounded-full" aria-label="Send" disabled={disabled || !text.trim()} onClick={send}><ArrowUpIcon /></InputGroupButton>
      </InputGroupAddon>
    </InputGroup>
  )
}
