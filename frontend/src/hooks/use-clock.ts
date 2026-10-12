import { createContext, useContext } from "react";

/** Source of the current time. Injected so tests can pin "now". */
export type Clock = () => Date;

export const systemClock: Clock = () => new Date();

/** Clock of the app; `AppProviders` replaces the default when given one (tests). */
export const ClockContext = createContext<Clock>(systemClock);

/** The current clock; call it when the time is needed, not once per render. */
export function useClock(): Clock {
  return useContext(ClockContext);
}
