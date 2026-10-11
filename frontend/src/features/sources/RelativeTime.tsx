import { useTranslation } from "react-i18next";

import { useClock } from "@/hooks/use-clock";
import { formatDateTime, formatRelativeTime } from "@/lib/intl";

/** An instant as "há 5 minutos" / "em 2 horas", with the full date and time on hover. */
export function RelativeTime({ value }: { value: string }) {
  const { i18n } = useTranslation();
  const clock = useClock();
  const date = new Date(value);
  return (
    <time dateTime={value} title={formatDateTime(date, i18n.language)}>
      {formatRelativeTime(date, clock(), i18n.language)}
    </time>
  );
}
