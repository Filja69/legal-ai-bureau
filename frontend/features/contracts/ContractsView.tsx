"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createContract, listContracts } from "@/api/contracts";
import { useAuth } from "@/hooks/useAuth";
import type { Contract, ContractType } from "@/types/contract";
import { Badge, Button, Card, CardHeader, PageHeader } from "@/components/ui";

const CONTRACT_TYPES: ContractType[] = ["service", "supply", "sale", "lease", "nda", "license", "other"];

export function ContractsView() {
  const { workspaceId } = useAuth();
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [title, setTitle] = useState("");
  const [rawText, setRawText] = useState("");
  const [contractType, setContractType] = useState<ContractType>("service");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    if (!workspaceId) return;
    try {
      setContracts(await listContracts(workspaceId));
    } catch {
      setError("Не удалось загрузить договоры — backend доступен?");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  async function handleUpload() {
    if (!title.trim() || !rawText.trim() || !workspaceId) return;
    setUploading(true);
    setError(null);
    try {
      await createContract(workspaceId, { title, raw_text: rawText, contract_type: contractType });
      setTitle("");
      setRawText("");
      await refresh();
    } catch {
      setError("Загрузка не удалась.");
    } finally {
      setUploading(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-muted">Выберите рабочее пространство, чтобы увидеть договоры.</div>;
  }

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <PageHeader
        title="Договоры"
        description="Анализ договоров — извлечение условий, поиск рисков, проверка через Юридическое исследование, двойная проверка юристами, редлайн. Есть два способа добавить договор: вставить текст вручную ниже, или загрузить файл (PDF/DOCX/TXT) на странице «Документы» и оттуда отправить его на проверку."
        actions={
          <Link href="/documents" className="rounded-lg border border-line bg-white px-3.5 py-2 text-sm font-semibold text-ink hover:bg-slate-50">
            Загрузить договор (файл)
          </Link>
        }
      />

      <Card className="mb-8">
        <CardHeader title="Или вставить текст вручную" />
        <div className="space-y-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Название"
            className="w-full rounded-lg border border-line bg-white p-2.5 text-sm text-ink placeholder:text-slate-400"
          />
          <select
            value={contractType}
            onChange={(e) => setContractType(e.target.value as ContractType)}
            className="rounded-lg border border-line bg-white p-2.5 text-sm text-ink"
          >
            {CONTRACT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="Вставьте текст договора"
            rows={8}
            className="w-full rounded-lg border border-line bg-white p-2.5 text-sm text-ink placeholder:text-slate-400"
          />
          <Button variant="primary" onClick={handleUpload} disabled={uploading || !title.trim() || !rawText.trim()}>
            {uploading ? "Загрузка..." : "Загрузить договор"}
          </Button>
        </div>
      </Card>

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <section>
        <h2 className="mb-3 text-lg font-semibold text-ink">Недавние договоры</h2>
        {contracts === null && <p className="text-sm text-muted">Загрузка…</p>}
        {contracts?.length === 0 && <p className="text-sm text-muted">Пока нет договоров.</p>}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {contracts?.map((c) => (
            <Link key={c.id} href={`/contracts/${c.id}`}>
              <Card className="h-full transition-shadow hover:shadow-panel">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-semibold text-ink">{c.title}</span>
                  {c.is_mock && <Badge tone="amber">MOCK</Badge>}
                </div>
                <div className="mt-2 text-xs text-muted">
                  {c.contract_type} · {c.status}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
