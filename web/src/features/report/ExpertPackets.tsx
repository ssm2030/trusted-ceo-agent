"use client";

import type {
  ExpertPacketViewItemV1,
  Issue,
} from "../../../../contracts/web-report/v1/generated/types";

import { renderExpertPacketMarkdown } from "@/features/report/model/expert-packet-markdown";
import styles from "@/features/report/ReportWorkspace.module.css";

type ExpertPacketsProps = {
  activeIssue: Issue;
  packets: ExpertPacketViewItemV1[];
};

function markdownHref(packet: ExpertPacketViewItemV1): string {
  return `data:text/markdown;charset=utf-8,${encodeURIComponent(
    renderExpertPacketMarkdown(packet),
  )}`;
}

export function ExpertPackets({
  activeIssue,
  packets,
}: ExpertPacketsProps) {
  return (
    <section aria-labelledby="expert-title" className={styles.section}>
      <header className={styles.sectionHeader}>
        <div>
          <p className={styles.sectionKicker}>단방향 검토 패킷</p>
          <h2 className={styles.sectionTitle} id="expert-title">
            전문가 검토 패킷 {packets.length}
          </h2>
          <p className={styles.sectionDescription}>
            화면·Markdown·인쇄 전용 패킷입니다. 전문가 답변은 이 웹에서
            수집하지 않습니다.
          </p>
        </div>
        <span className={styles.scopeBand}>
          현재 범위: {activeIssue.title_template}
        </span>
      </header>

      {packets.length === 0 ? (
        <p className={styles.empty}>
          현재 문제에 검증 엔진이 게시한 전문가 패킷이 없습니다.
        </p>
      ) : (
        <div className={styles.packetList}>
          {packets.map((packet, index) => (
            <article
              className={styles.packet}
              id={`expert-packet-${packet.expert_packet_id}`}
              key={packet.expert_packet_id}
            >
              <header className={styles.packetHeader}>
                <div>
                  <p className={styles.sectionKicker}>
                    전문가 패킷 {index + 1}
                  </p>
                  <h3>{packet.profession} 검토 요청</h3>
                  <p className={styles.packetMeta}>
                    {packet.expert_packet_id} · 리비전 {packet.revision}
                  </p>
                </div>
                <div className={styles.downloadActions}>
                  <a
                    className={styles.actionLink}
                    download={`${packet.expert_packet_id}.md`}
                    href={markdownHref(packet)}
                  >
                    Markdown 내려받기
                  </a>
                  <button
                    className={styles.actionButton}
                    onClick={() => window.print()}
                    type="button"
                  >
                    인쇄 보기
                  </button>
                </div>
              </header>

              <div className={styles.packetColumns}>
                <div>
                  <h4>검토 질문</h4>
                  <p>{packet.review_question}</p>
                </div>
                <div>
                  <h4>결론 금지 범위</h4>
                  <ul>
                    {packet.forbidden_conclusions.map((conclusion) => (
                      <li key={conclusion}>{conclusion}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4>미해결 불확실성</h4>
                  <ul>
                    {packet.unresolved_uncertainties.map((uncertainty) => (
                      <li key={uncertainty}>{uncertainty}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4>필요 문서 참조</h4>
                  <ul>
                    {packet.required_document_refs.map((reference) => (
                      <li className={styles.hash} key={reference}>
                        {reference}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
