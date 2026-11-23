import {
  BotIcon,
  BugIcon,
  CrosshairIcon,
  FileTextIcon,
  FlagIcon,
  GraduationCapIcon,
  MessageCircleIcon,
  SearchIcon,
  ShieldIcon,
  SparklesIcon,
  TerminalIcon,
  UserSearchIcon,
  type LucideIcon,
} from 'lucide-react';

/**
 * Icons a personality can use, by lucide name. A fixed map (no dynamic lookup into lucide)
 * keeps the bundle small; unknown names fall back to the bot icon.
 */
export const PERSONALITY_ICONS: Record<string, LucideIcon> = {
  bot: BotIcon,
  'message-circle': MessageCircleIcon,
  flag: FlagIcon,
  crosshair: CrosshairIcon,
  shield: ShieldIcon,
  bug: BugIcon,
  search: SearchIcon,
  'file-text': FileTextIcon,
  'graduation-cap': GraduationCapIcon,
  'user-search': UserSearchIcon,
  terminal: TerminalIcon,
  sparkles: SparklesIcon,
};

export function PersonalityIcon({
  name,
  className,
}: {
  name: string | null | undefined;
  className?: string;
}) {
  const Icon = (name && PERSONALITY_ICONS[name]) || BotIcon;
  return <Icon className={className} aria-hidden="true" />;
}
