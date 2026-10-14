/** Sub-path of the creation screen, `/w/:workspaceId/widgets/new`. */
export const NEW_WIDGET_PATH = "new";

/** The widget list of a workspace. */
export function widgetsPath(workspaceId: string): string {
  return `/w/${workspaceId}/widgets`;
}

/** A widget's screen (`widgetId` = `new` creates one). */
export function widgetPath(workspaceId: string, widgetId: string): string {
  return `${widgetsPath(workspaceId)}/${widgetId}`;
}
