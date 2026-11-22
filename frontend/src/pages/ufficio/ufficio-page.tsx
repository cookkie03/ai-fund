import { useParams } from "react-router-dom";
import { AgentView } from "./agent-view";
import { Overview } from "./overview";

/** /ufficio is the office overview; /ufficio/:agent opens that agent's chats and tool stream. */
export function UfficioPage() {
  const { agent } = useParams();
  return agent ? <AgentView key={agent} agent={agent} /> : <Overview />;
}
