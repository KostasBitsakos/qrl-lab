# Style guide: writing like C. Bitsakos

Sources (page = PDF page): DERP (CloudCom 2018), QuantuML (LNCS manuscript), DInos (DEXA 2025),
RS = `Sofia_paper2025.pdf` ("The Resourcerer Supreme", IEEE Access manuscript, his), thesis (Mariana Trench,
diploma thesis 2017: abstract p7, ch. 3 pp23-25, ch. 7 pp59-62).

## Imitate

1. **Voice: "we", active.** "In this work we present DERP, a system that deals with the elasticity issue"
   (DERP p1). "In this paper, we introduce the Resourcerer Supreme (RS), a ..." (RS p1). (Name + appositive.) Passive appears mainly for experiments ("Our experiments were
   conducted on IBM's Quantum platform", QuantuML p2).
2. **Section openings.** Introductions open with the platform and the problem, then the HPA limitation:
   "Traditional threshold-based mechanisms (e.g., HPA) often fail to anticipate sudden demand surges"
   (DInos p1). Related work opens with the standard mechanism (HPA, VPA, Cluster Autoscaler; RS p2,
   DInos p2; Amazon auto-scaling, DERP p1).
3. **Lineage before contribution.** He places the new system after his earlier one: "our previous work
   introduced DERP" (DInos p2), then "Building on these improvements, we propose our main contribution:"
   (DInos p2), "Building upon these insights, we introduce three key advancements. First, ... Second, ..."
   (RS p2). Contributions are **prose with First/Second/Furthermore**, never bullets.
4. **Roadmap paragraph.** "The paper is structured as follows: Section 1 provides ..." (QuantuML p2);
   thesis "Thesis Structure" (p25).
5. **Acronyms defined once and then used:** "Horizontal Pod Autoscaler (HPA)",
   "Deep Reinforcement Learning (Deep RL)" (DInos p1-2); he writes "Deep RL", not "DRL", in recent papers.
6. **Related work pattern.** One thread per paragraph; "Author et al. [n] introduced X, while Author et al. [m]
   developed Y" (RS p3). Each
   paragraph closes with how the cited line relates to his work: "Nevertheless, this approach also struggles
   with large space of states." (DERP p2); "Unlike previous methods that ..., DInos ..." (DInos p3). Ends with "In summary, ..." (RS p3, DInos p3).
7. **Vocabulary:** elasticity, elastic resource provisioning, proactive vs. reactive scaling, workload
   spikes, over-provisioning, custom reward function, accumulated reward, stateless Redis.
8. **Tense:** present for systems ("DInos utilizes a customizable reward function", DInos p1), present
   perfect for the field ("has emerged as a leading platform", RS p1), past for runs.
9. **Spelling:** British in 2018 ("behaviour", "optimise", DERP p1), American since (RS, DInos: "behavior",
   "optimization", "utilization"). **Use American.**
10. **Figures/sections:** written out, "Figure 1", "Section V"; often parenthetical "(Figure 1)" (DInos p3).

## Do not copy

- **Overclaims and unbacked superiority:** "theoretically demonstrate its supremacy over classical algorithms"
  (QuantuML p1); "adapts seamlessly to varying
  workloads, thereby outperforming existing ML-based autoscaling methods" (RS p3, no comparison shown);
  "ensuring", "significantly", "robust" without evidence.
- **Long sentences with -ing tails** ("..., thereby enhancing resource efficiency and ensuring consistent
  performance", RS p2). Keep his structure, cut the tails; short, varied sentences.
- **Repetition:** the same headline numbers in abstract, intro, related work and conclusion (RS p1-3,
  DInos p1-3); a paragraph printed twice (RS p2).
- **Buzzwords:** "leverages", "advanced", "cutting edge", "key advancements". Prefer "uses", plain verbs.
- **Random capitals** ("Quantum Computing", "Classical Models", QuantuML p1). Lower case for common nouns.
- **"Our previous work"** is his habit, but double-blind venues need third-person self-citation.

## Applied to Sofia

Abstract: problem -> "In this paper, we introduce Sofia, a ..." -> method -> protocol -> scope limit.
Introduction: context -> HPA limitation -> DERP/DInos lineage -> quantum motivation -> "In this paper, we
introduce" -> "First, ... Second, ..." -> "The rest of the paper is structured as follows."
Related work: one thread per paragraph, each closing with its link to Sofia; short "In summary" paragraph
without novelty claims.
