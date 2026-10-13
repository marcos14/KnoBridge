import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { NewConversationInput } from "@/lib/api/conversations";
import { type Product, useProducts } from "@/lib/api/products";

import { chatErrorMessage } from "./chatErrors";
import { Composer } from "./Composer";
import { LevelPicker } from "./LevelPicker";
import { NoCollectionsHint } from "./NoCollectionsHint";

interface NewConversationProps {
  workspaceId: string;
  /** Whether the member may configure products (gets a link when there is none to talk to). */
  canManageProducts: boolean;
  /** Creates the conversation and sends the first question; rejects on error. */
  onStart: (conversation: NewConversationInput, content: string) => Promise<void>;
}

/** The chat root: pick an active product and a level, then ask the first question. */
export function NewConversation({ workspaceId, canManageProducts, onStart }: NewConversationProps) {
  const { t } = useTranslation();
  const products = useProducts(workspaceId);

  if (products.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("chat.products.loading")}
      </p>
    );
  }
  if (products.isError) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p role="alert" className="text-sm">
          {t("chat.products.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void products.refetch();
          }}
        >
          {t("chat.retry")}
        </Button>
      </div>
    );
  }
  // Viewers already get only the active ones; the other roles see every product.
  const active = products.data.filter((product) => product.active);
  const [first] = active;
  if (first === undefined) {
    return (
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">{t("chat.products.noneTitle")}</h2>
        <p className="text-muted-foreground text-sm">
          {canManageProducts ? t("chat.products.noneManager") : t("chat.products.noneMember")}
        </p>
        {canManageProducts && (
          <Link to={`/w/${workspaceId}/products`} className="text-sm underline underline-offset-4">
            {t("chat.products.goToProducts")}
          </Link>
        )}
      </div>
    );
  }
  return <StartForm products={active} first={first} onStart={onStart} />;
}

interface StartFormProps {
  products: readonly Product[];
  first: Product;
  onStart: NewConversationProps["onStart"];
}

function StartForm({ products, first, onStart }: StartFormProps) {
  const { t } = useTranslation();
  const labelId = useId();
  // The level starts at the member's maximum in the product, and goes back to it on each change.
  const [choice, setChoice] = useState<NewConversationInput>({
    productId: first.id,
    level: first.my_max_level,
  });
  const [failure, setFailure] = useState<string | null>(null);
  const chosen = products.find((product) => product.id === choice.productId) ?? first;

  return (
    <div className="flex flex-1 flex-col justify-end gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold">{t("chat.newTitle")}</h2>
        <p className="text-muted-foreground text-sm">{t("chat.newDescription")}</p>
      </div>
      <div className="flex flex-col gap-2">
        <span id={labelId} className="text-sm font-medium">
          {t("chat.products.label")}
        </span>
        <Select
          value={chosen.id}
          onValueChange={(productId) => {
            const next = products.find((product) => product.id === productId) ?? first;
            setChoice({ productId: next.id, level: next.my_max_level });
          }}
        >
          <SelectTrigger aria-labelledby={labelId} className="w-full sm:w-80">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {products.map((product) => (
              <SelectItem key={product.id} value={product.id}>
                {product.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {chosen.description !== "" && (
          <p className="text-muted-foreground text-xs">{chosen.description}</p>
        )}
      </div>
      <LevelPicker
        maxLevel={chosen.my_max_level}
        value={choice.level}
        onChange={(level) => {
          setChoice({ productId: chosen.id, level });
        }}
      />
      {failure !== null && <FormAlert key={failure} message={failure} />}
      <NoCollectionsHint product={chosen} />
      <Composer
        onSend={async (content) => {
          setFailure(null);
          try {
            await onStart({ productId: chosen.id, level: choice.level }, content);
            return true;
          } catch (error) {
            setFailure(chatErrorMessage(error, t));
            return false;
          }
        }}
      />
    </div>
  );
}
