import { useId } from "react";
import { useTranslation } from "react-i18next";

import { FilterSelect } from "@/components/FilterSelect";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CONVERSATION_CHANNELS,
  type ConversationFilters,
  hasConversationFilters,
  parseChannel,
} from "@/lib/conversationFilters";

/** Value of the "no filter" item: Radix Select items cannot have an empty value. */
const ALL = "all";

/** Something a filter offers by id: an assistant or a member. */
export interface FilterChoice {
  id: string;
  name: string;
}

interface ConversationFilterBarProps {
  filters: ConversationFilters;
  assistants: readonly FilterChoice[];
  users: readonly FilterChoice[];
  onChange: (filters: ConversationFilters) => void;
}

/** A shared link may name an id no longer listed: keep it selectable, by id. */
function withChosen(choices: readonly FilterChoice[], chosen: string | undefined, name: string) {
  return chosen === undefined || choices.some((choice) => choice.id === chosen)
    ? choices
    : [...choices, { id: chosen, name }];
}

/**
 * Assistant, user, channel, creation period and "only 👎" of the conversations; each change
 * applies now.
 */
export function ConversationFilterBar({
  filters,
  assistants,
  users,
  onChange,
}: ConversationFilterBarProps) {
  const { t } = useTranslation();
  const assistantId = useId();
  const userId = useId();
  const channelId = useId();
  const fromId = useId();
  const toId = useId();
  const negativeId = useId();
  const assistantOptions = withChosen(
    assistants,
    filters.assistant,
    t("conversations.unknownAssistant", { id: filters.assistant }),
  );
  const userOptions = withChosen(
    users,
    filters.user,
    t("conversations.unknownUser", { id: filters.user }),
  );

  function change(patch: Partial<ConversationFilters>) {
    onChange({ ...filters, ...patch });
  }

  return (
    <fieldset className="flex flex-wrap items-end gap-4">
      <legend className="sr-only">{t("conversations.filters.label")}</legend>
      <div className="flex flex-col gap-2">
        <Label htmlFor={assistantId}>{t("conversations.filters.assistant")}</Label>
        <FilterSelect
          id={assistantId}
          className="w-full sm:w-56"
          value={filters.assistant ?? ALL}
          options={[
            { value: ALL, label: t("conversations.filters.allAssistants") },
            ...assistantOptions.map((choice) => ({ value: choice.id, label: choice.name })),
          ]}
          onValueChange={(value) => {
            change({ assistant: value === ALL ? undefined : value });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={userId}>{t("conversations.filters.user")}</Label>
        <FilterSelect
          id={userId}
          className="w-full sm:w-56"
          value={filters.user ?? ALL}
          options={[
            { value: ALL, label: t("conversations.filters.allUsers") },
            ...userOptions.map((choice) => ({ value: choice.id, label: choice.name })),
          ]}
          onValueChange={(value) => {
            change({ user: value === ALL ? undefined : value });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={channelId}>{t("conversations.filters.channel")}</Label>
        <FilterSelect
          id={channelId}
          className="w-full sm:w-40"
          value={filters.channel ?? ALL}
          options={[
            { value: ALL, label: t("conversations.filters.allChannels") },
            ...CONVERSATION_CHANNELS.map((channel) => ({
              value: channel,
              label: t(`conversations.filters.channels.${channel}`),
            })),
          ]}
          onValueChange={(value) => {
            change({ channel: parseChannel(value) });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={fromId}>{t("conversations.filters.from")}</Label>
        <Input
          id={fromId}
          type="date"
          className="w-full sm:w-44"
          value={filters.from ?? ""}
          max={filters.to}
          onChange={(event) => {
            change({ from: event.target.value || undefined });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={toId}>{t("conversations.filters.to")}</Label>
        <Input
          id={toId}
          type="date"
          className="w-full sm:w-44"
          value={filters.to ?? ""}
          min={filters.from}
          onChange={(event) => {
            change({ to: event.target.value || undefined });
          }}
        />
      </div>
      <div className="flex h-9 items-center gap-2">
        <Checkbox
          id={negativeId}
          checked={filters.negative === true}
          onCheckedChange={(checked) => {
            change({ negative: checked === true ? true : undefined });
          }}
        />
        <Label htmlFor={negativeId}>{t("conversations.filters.negative")}</Label>
      </div>
      {hasConversationFilters(filters) && (
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onChange({});
          }}
        >
          {t("conversations.filters.clear")}
        </Button>
      )}
    </fieldset>
  );
}
