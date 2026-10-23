> This note is background reading on how a health-intervention systematic review is conducted. The operating instructions for this repository are the skills in `.agents/skills/` and the [user manual](user-manual.md). This note does not provide medical advice.

A–Z workflow for conducting a systematic review
===============================================

This is a practical workflow for a health-intervention systematic review, with meta-analysis where appropriate. Diagnostic, prognostic, prevalence, qualitative and scoping reviews use related but different methods.

The complete pathway is:

Identify a genuine evidence gap → formulate the question → assemble the team → write and register the protocol → design and peer-review the search → retrieve and deduplicate records → screen studies → extract data → assess risk of bias → synthesize results → assess certainty → write and report → submit → archive and update.

A systematic review is itself a research project. Meta-analysis is an optional statistical component of a systematic review; it should not be performed when the studies cannot reasonably be combined.
PRISMA is primarily a reporting guideline, not a complete manual for conducting the review. For conduct, use a methodological handbook such as the Cochrane Handbook; use PRISMA 2020 to ensure complete reporting.

Phase 1: Decide what kind of review is needed
=============================================

1. Define the intended decision
-------------------------------

Ask:

- Who will use the review?
- What decision should it inform?
- Is the question about treatment, harm, diagnosis, prognosis, prevalence, association, implementation or patient experience?
- Is a systematic review actually necessary?
- Is the purpose to estimate an effect, map a field or explain experiences?

Choose the review design accordingly:

| Purpose | Appropriate review |
| --- | --- |
| Estimate benefits or harms of an intervention | Intervention systematic review |
| Estimate diagnostic accuracy | Diagnostic-test accuracy review |
| Estimate prevalence | Prevalence review |
| Examine an exposure–outcome association | Etiological/exposure review |
| Predict future outcomes | Prognostic review |
| Synthesize patient experiences | Qualitative evidence synthesis |
| Map concepts, evidence types and gaps | Scoping review |
| Produce evidence rapidly with explicit shortcuts | Rapid review |
| Keep evidence continuously current | Living systematic review |

Do not call a narrative literature review “systematic” merely because several databases were searched.

2. Conduct a preliminary scoping search
---------------------------------------

Before committing months of work, search:

- PubMed/MEDLINE
- Cochrane Database of Systematic Reviews
- PROSPERO
- Relevant guideline repositories
- Recent journals in the specialty
- Epistemonikos or another evidence-synthesis database
- Google Scholar as a supplementary discovery source

Look for:

- Existing reviews with the same PICO
- Dates of their final searches
- Whether newer primary studies have appeared
- Weaknesses in previous reviews
- Ongoing registered reviews
- Whether sufficient primary research exists
- Whether the literature is too heterogeneous for the proposed question

Create an “existing-review map”:

| Review | Search date | Population | Intervention | Study designs | Main weakness | Need for new review |
| --- | --- | --- | --- | --- | --- | --- |

3. Make a go/no-go decision
---------------------------

Proceed when at least one of these is true:

- No rigorous review addresses the question.
- The existing review is outdated.
- Important new studies may change the conclusion.
- Earlier reviews used poor methods.
- Existing reviews used different populations, interventions or outcomes.
- Results of previous reviews conflict.
- A clinically important subgroup has not been examined.
- New methods permit a better synthesis.
- Do not proceed simply because the topic is interesting. A new review should fill a demonstrable evidence gap.

Phase 2: Build the review team
==============================

A rigorous review should not normally be performed by one person. Cochrane requires independent human involvement in consequential stages and does not publish single-person reviews.

A strong team includes:

- Lead reviewer/project manager
- Subject-matter or clinical expert
- Systematic-review methodologist
- Information specialist or medical librarian
- Statistician or meta-analysis expert
- At least two independent screeners/extractors
- Third reviewer for unresolved disagreements
- Patient or public representative when appropriate
- Language expertise if non-English reports are likely

Agree before beginning:

- Roles and responsibilities
- Authorship expectations
- CRediT contributor roles
- Communication method
- Conflict-resolution process
- File-storage location
- Data-security requirements
- Meeting schedule
- Target journal
- Approximate timeline
- Conflict-of-interest declarations
- Do not promise authorship solely for routine screening. Authorship requires meaningful intellectual contribution and accountability.

Phase 3: Formulate the research question
========================================

4. Use the correct question framework
-------------------------------------

For intervention reviews, use PICO:

- P — Population: Who has the condition or problem?
- I — Intervention: What treatment, policy or exposure is being evaluated?
- C — Comparator: What is the alternative?
- O — Outcomes: What consequences matter?
- S — Study design: Which study designs can answer the question?
- T — Time: At what follow-up times?

Example:

In adults with hypertension, does home blood-pressure telemonitoring plus usual care, compared with usual care alone, reduce blood pressure and cardiovascular events without increasing adverse events?

Expanded PICOST:

| Element | Example specification |
| --- | --- |
| Population | Adults aged ≥18 years with diagnosed hypertension |
| Intervention | Home BP measurement with electronic transmission to a healthcare professional and feedback |
| Comparator | Usual care, clinic-based monitoring or home monitoring without transmission |
| Outcomes | Systolic BP, diastolic BP, BP control, cardiovascular events, adverse events, treatment burden |
| Study design | Individually randomized or cluster-randomized controlled trials |
| Time | Short term: <6 months; medium term: 6–12 months; long term: >12 months |
| Setting | Primary care, outpatient or community care |

Other frameworks include:

- PECO: population, exposure, comparator, outcome
- PIRD: population, index test, reference standard, diagnosis
- PICo: population, phenomenon of interest, context
- SPIDER: sample, phenomenon, design, evaluation, research type
- CoCoPop: condition, context, population for prevalence questions

5. Test whether the question is answerable
------------------------------------------

The question should be:

- Clinically or scientifically important
- Specific enough to produce interpretable results
- Broad enough to find usable evidence
- Consistent with the intended review design
- Feasible with available time, access and expertise
- Defined before results are examined

Warning signs include:

- Several unrelated populations
- Multiple fundamentally different interventions
- Vague outcomes such as “success”
- No meaningful comparator
- Mixing treatment effects, diagnosis and prevalence
- Attempting dozens of subgroups
- Inclusion criteria that cannot be applied consistently

Phase 4: Create the title and objectives
========================================

6. Construct a precise working title
------------------------------------

A useful formula is:

[Intervention] versus [comparator] for [population/condition]: a systematic review and meta-analysis of [study design]

Example:

Home blood-pressure telemonitoring plus usual care versus usual care for adults with hypertension: a systematic review and meta-analysis of randomized controlled trials

If meta-analysis is not certain, initially use:

“…a systematic review”

Add “and meta-analysis” only when quantitative pooling is actually performed.

Avoid:

- “A study of…”
- “Impact of…” when causal effects cannot be estimated
- “Everything about…”
- Titles that claim effectiveness before the review is conducted
- Unnecessary abbreviations
- “PRISMA systematic review”—PRISMA is a reporting standard, not a review type

7. Write the primary objective
------------------------------

Example:

To evaluate the benefits and harms of home blood-pressure telemonitoring plus usual care compared with usual care or non-transmitting home monitoring in adults with hypertension.

Secondary objectives might include:

- Whether effects differ by intervention intensity
- Whether effects differ by baseline blood pressure
- Whether effects differ between primary-care and specialist settings
- Whether effects persist beyond 12 months
- Subgroup objectives should be biologically or clinically justified and prespecified. Do not create them after seeing interesting results.

Phase 5: Define the eligibility criteria
========================================

8. Write operational inclusion and exclusion criteria
-----------------------------------------------------

The criteria must be detailed enough that two reviewers can apply them independently.

Example:

| Domain | Include | Exclude |
| --- | --- | --- |
| Population | Adults ≥18 years with diagnosed primary hypertension | Paediatric populations; pregnancy-only cohorts; secondary hypertension-only cohorts |
| Mixed population | Include if ≥80% meet criteria or eligible subgroup data are available | Mixed population with inseparable eligible data |
| Intervention | Home BP monitoring with electronic transmission and professional feedback | Clinic-only monitoring; self-monitoring without data transmission; monitoring without a BP component |
| Comparator | Usual care, clinic monitoring, or non-transmitting home monitoring | No concurrent comparator |
| Design | Individual or cluster RCT | Observational studies, uncontrolled before–after studies, case reports |
| Outcomes | Studies measuring at least one prespecified outcome | Studies that clearly did not measure any relevant outcome |
| Setting | Primary care, outpatient, community | Inpatient-only acute-care monitoring |
| Duration | Minimum four weeks, if clinically justified | Intervention shorter than four weeks |
| Language | No language restriction | None based solely on language |
| Publication status | Published, unpublished, registry results, dissertations and eligible conference reports | Commentary, editorial, protocol without results |
| Date | Database inception to final search date | Date exclusions only if scientifically justified |

Important distinction:

- A study is the underlying experiment.
- A report is an article, abstract, registry entry, dissertation or other document describing that study.
- One study may produce multiple reports. These must be linked and treated as one study.
- Do not exclude an otherwise eligible study simply because its results are inconvenient, nonsignificant, incompletely reported or unusable for meta-analysis. A study can be included in the systematic review but absent from a particular quantitative synthesis.

9. Define outcomes in detail
----------------------------

For every outcome, prespecify:

- Outcome domain
- Exact definition
- Preferred measurement instrument
- Acceptable alternative instruments
- Direction of benefit
- Follow-up time points
- Whether change scores or final values are preferred
- Whether adjusted or unadjusted results are preferred
- Whether outcome assessors must be blinded
- Which outcome is primary
- Which outcomes are important or critical

Example:

| Outcome | Definition | Measure | Time point |
| --- | --- | --- | --- |
| Primary efficacy | Systolic BP | Mean clinic SBP in mmHg | Closest to 6 months |
| Secondary efficacy | Diastolic BP | Mean clinic DBP in mmHg | Closest to 6 months |
| BP control | Participants reaching study-defined target | Risk ratio | Closest to 12 months |
| Major cardiovascular events | Study-defined composite | Risk ratio or hazard ratio | Longest follow-up |
| Safety | Serious adverse events | Participants with ≥1 event | Longest follow-up |
| Acceptability | Withdrawal for any reason | Risk ratio | End of intervention |

Create a hierarchy for multiple measurements. For example:

- Validated ambulatory measurement
- Standardized clinic measurement
- Home measurement
- Self-reported value
- Without a hierarchy, reviewers may unconsciously choose the most favorable result.

Phase 6: Write and register the protocol
========================================

10. Prepare the protocol before formal screening
------------------------------------------------

Use PRISMA-P. It contains the minimum elements that should appear in a systematic-review protocol.

The protocol should include:

- Administrative details
- Title
- Review team and affiliations
- Corresponding author
- Contributions
- Guarantor
- Funding
- Sponsor’s role
- Conflicts of interest
- Planned start and completion dates
- Amendment policy
- Background
- Description of the condition
- Description of the intervention
- How the intervention might work
- Why the review is needed
- Limitations of existing reviews
- Objectives
- Primary question
- Secondary questions
- Planned subgroup questions
- Methods
- Eligibility criteria
- Information sources
- Draft search strategy
- Study-record management
- Deduplication process
- Screening process
- Full-text exclusion reasons
- Data-extraction process
- Outcomes and prioritization
- Risk-of-bias tool
- Effect measures
- Synthesis groups
- Meta-analysis model
- Heterogeneity assessment
- Subgroup analysis
- Sensitivity analysis
- Missing-data handling
- Reporting-bias assessment
- Certainty-of-evidence method
- Software
- Data-sharing plan
- Use of AI or automation

11. Register prospectively
--------------------------

For eligible health-related reviews, register with PROSPERO. If the review is not eligible, use OSF or another permanent registry.
Registration should happen before formal screening wherever possible. PROSPERO is designed to reduce undisclosed duplication and make deviations from planned methods visible.

Registration is not the same as publishing a complete protocol. Ideally:

- Register the core protocol.
- Deposit or publish the full protocol.
- Date and version it.
- Never silently overwrite it.

Maintain an amendment log:

| Date | Original method | New method | Reason | Made before or after seeing results? | Likely impact |
|---|---|---|---|---|
Protocol deviations are not automatically misconduct. Undisclosed outcome switching is the problem.

Phase 7: Design the search strategy
===================================

12. Select information sources
------------------------------

For a health-intervention review, common core sources are:

- MEDLINE/PubMed or MEDLINE/Ovid
- Embase
- Cochrane CENTRAL

Add subject-specific sources where appropriate:

- CINAHL for nursing and allied health
- PsycINFO for psychology and mental health
- Web of Science or Scopus for interdisciplinary citation searching
- SPORTDiscus for exercise
- ERIC for education
- Global Index Medicus for broader geographical coverage
- ClinicalTrials.gov
- WHO ICTRP
- Regulatory-agency sources
- Dissertations and thesis databases
- Conference proceedings
- Relevant preprint servers
- Reference lists of included studies and related reviews
- Forward citation searching
- Contact with experts or study authors
- Google Scholar may supplement the search but is rarely adequate as the principal database because its indexing, reproducibility and export functions are limited.

13. Convert the PICO into searchable concepts
---------------------------------------------

Do not automatically search every PICO element. Outcomes and comparators are often poorly described in titles and abstracts and can make the search dangerously narrow.

For many intervention reviews, the search contains:

- Population/condition terms
- Intervention terms
- A validated study-design filter
- Within each concept, combine synonyms using OR. Combine concepts using AND.

Conceptual structure:

(Population term 1 OR Population term 2 OR Population term 3)
AND
(Intervention term 1 OR Intervention term 2 OR Intervention term 3)
AND
(Randomized-trial filter)

14. Identify search terms
-------------------------

For each concept, collect:

- Controlled vocabulary: MeSH, Emtree or database-specific headings
- Common terminology
- Historical terminology
- Abbreviations
- British and American spellings
- Drug generic names
- Brand names
- Device names
- Acronyms
- Common misspellings
- Singular and plural forms
- Relevant phrases
- Broader and narrower terms

Sources of terminology include:

- Sentinel articles known to be eligible
- Existing high-quality reviews
- Clinical guidelines
- Database subject-heading browsers
- Keywords from relevant papers
- Text-mining tools
- Expert consultation

15. Create a reproducible search string
---------------------------------------

Simplified PubMed teaching example:

(
"Hypertension"[Mesh]
OR hypertens*[tiab]
OR "high blood pressure"[tiab]
)
AND
(
"Telemedicine"[Mesh]
OR telemonitor*[tiab]
OR "remote monitor*"[tiab]
OR "home blood pressure monitor*"[tiab]
OR "self-monitor* blood pressure"[tiab]
)
AND
(
randomized controlled trial[pt]
OR controlled clinical trial[pt]
OR random*[tiab]
OR placebo[tiab]
OR trial[tiab]
)
NOT
(
animals[mh] NOT humans[mh]
)
This is only a teaching example. A final strategy should be reviewed by an information specialist.

Technical details to check:

- Correct parentheses
- Correct Boolean operators
- Phrase searching
- Truncation symbols
- Proximity operators
- Field tags
- Subject-heading explosion
- Spelling variants
- Singular/plural forms
- Database-specific syntax
- Whether the search retrieves known eligible studies
- Whether filters exclude recent, unindexed records
- Do not copy a PubMed string directly into Embase. Translate its logic into each database’s syntax.

16. Validate and peer-review the search
---------------------------------------

Test the strategy against several known eligible “sentinel” studies. If the search cannot retrieve them, determine why.
Have a librarian or information specialist peer-review the principal strategy using the PRESS guideline. Cochrane strongly recommends search-strategy peer review before execution.

17. Execute and document every search
-------------------------------------

For each source, record:

- Database name
- Platform/provider
- Coverage dates
- Exact search date
- Complete search string exactly as run
- Filters or limits
- Number retrieved
- Name of searcher
- Export format
- Export filename
- Any search errors
- Whether the search was updated

Example search log:

| Source | Platform | Date | Records | File |
| --- | --- | --- | --- | --- |
| MEDLINE | Ovid | 2026-07-28 | 1,842 | medline_2026-07-28.ris |
| Embase | Elsevier | 2026-07-28 | 2,310 | embase_2026-07-28.ris |
| CENTRAL | Cochrane Library | 2026-07-28 | 936 | central_2026-07-28.ris |

Use PRISMA-S when reporting the search.

Phase 8: Manage references and deduplicate
==========================================

18. Preserve the raw exports
----------------------------

Never alter the only copy of the raw search results.

Recommended structure:

review-project/
├── 00_protocol/
├── 01_search/
│   ├── raw_exports/
│   ├── search_strategies/
│   └── search_log/
├── 02_deduplication/
├── 03_screening/
├── 04_full_texts/
├── 05_extraction/
├── 06_risk_of_bias/
├── 07_analysis/
├── 08_figures_tables/
├── 09_manuscript/
└── 10_archive/

Use file names containing:

- Source
- Date
- Version
- Processing stage

19. Deduplicate systematically
------------------------------

Deduplication may compare:

- DOI
- PMID
- Trial registration number
- Exact title
- Normalized title
- First author
- Year
- Journal
- Volume and pages

Keep a log of:

- Total imported
- Automatically identified duplicates
- Manually confirmed duplicates
- Records remaining
- Software and algorithm used
- Do not confuse duplicate database records with multiple publications from the same study. Database duplicates can be merged before screening; multiple reports of a study must be linked without discarding unique information.

Phase 9: Screen titles and abstracts
====================================

20. Build the screening form
----------------------------

Convert eligibility criteria into operational questions:

- Is the population potentially eligible?
- Is the intervention potentially eligible?
- Is there a potentially eligible comparator?
- Is the study design potentially eligible?
- Is this a primary report or additional report of a potentially eligible study?

Title/abstract options are usually:

- Include
- Exclude
- Unclear/maybe
- At this stage, be over-inclusive. If information is insufficient, retain the record for full-text screening.

21. Pilot the criteria
----------------------

Before screening everything:

- Select a varied sample.
- Have both reviewers screen it independently.
- Compare disagreements.
- Identify vague criteria.
- Revise the operational guidance.
- Repeat until the criteria can be applied consistently.
- Do not modify eligibility criteria merely to remove inconvenient studies. Any substantive change must be documented as a protocol amendment.

22. Conduct independent screening
---------------------------------

Ideally, two reviewers independently screen every title and abstract.

Reviewers should not see each other’s decision before submitting their own. Resolve disagreements by:

- Discussion
- Consulting the full text
- Applying the written criteria
- Third-reviewer adjudication if necessary
- At title/abstract screening, it is generally safer to include a doubtful record than to exclude a potentially eligible study.

Record:

- Reviewer identity
- Decision
- Date
- Any label or note
- Conflict resolution

Phase 10: Screen full texts
===========================

23. Retrieve the reports
------------------------

Obtain full texts through:

- Institutional subscriptions
- Interlibrary loan
- Author contact
- Repositories
- Publisher sites
- Trial registries
- Regulatory documents
- Preprint servers
- Do not label a paper “excluded” merely because it cannot initially be found. Track it as “full text not retrieved” and document retrieval attempts.

24. Apply full-text criteria independently
------------------------------------------

At least two people should independently make final eligibility decisions. This is a mandatory Cochrane expectation because study inclusion is one of the most influential judgments in a review.

When a prospectively approved AI-exception method is used instead of duplicate
human screening, record it as a protocol amendment and preserve equivalent
audit safeguards. Reuse the approved eligibility source; extract embedded text;
OCR only defective pages; store all candidate reports, page provenance,
immutable evidence packets, append-only reviewer runs, and decision events in
`full_text_screening.sqlite`; use one fresh context per study and reviewer;
invoke an independent Reviewer B only for valid high-confidence Reviewer A
candidates; route unclear, conflicting, inaccessible, poor-OCR, or
uncertain-linkage cases to humans; audit automatic decisions; and require final
human batch approval before locking. Preserve excluded reports for audit and
export only included studies/reports to the separate full-text extraction
dataset.

For every excluded full text, assign one primary reason.

Recommended reason hierarchy:

- Wrong population
- Wrong intervention
- Wrong comparator
- Wrong study design
- Wrong outcome—not measured, rather than merely unreported
- Insufficient duration
- Wrong setting
- Duplicate report with no additional usable information
- No primary results
- Unable to retrieve sufficient information

Use specific reasons:

- Good: “Participants were all younger than 16 years.”
- Poor: “Not relevant.”
- Good: “Home BP readings were not transmitted to a healthcare professional.”
- Poor: “Wrong intervention.”

25. Link reports belonging to the same study
--------------------------------------------

Use:

- Trial registration number
- Author names
- Recruitment dates
- Sample size
- Study sites
- Intervention details
- Baseline characteristics
- Funding source

Assign:

- One unique study ID
- Separate report IDs for each publication

Example:

Study ID: SMITH-HTN-2019

Reports:

- SMITH-HTN-2019-primary
- SMITH-HTN-2019-protocol
- SMITH-HTN-2019-followup
- SMITH-HTN-2019-registry
- The primary publication is not automatically the only source of data.

26. Maintain PRISMA counts
--------------------------

Track:

- Records identified from databases
- Records from other sources
- Duplicates removed
- Records screened
- Records excluded at title/abstract stage
- Full texts sought
- Full texts not retrieved
- Full texts assessed
- Full texts excluded by reason
- Studies included
- Reports of included studies
- Studies included in each synthesis
- The number of reports may exceed the number of studies.

Phase 11: Design and pilot data extraction
==========================================

27. Create a structured extraction form
---------------------------------------

Extract only data needed to answer the review question, describe the evidence, assess bias or interpret applicability.
Identification
Study ID
Report ID
Citation
DOI/PMID
Trial registration
Country
Language
Publication status
Funding
Author conflicts of interest
Study characteristics
Study design
Number of centres
Recruitment dates
Setting
Inclusion/exclusion criteria
Randomization unit
Planned sample size
Actual sample size
Follow-up duration
Participants
Number randomized
Number analyzed
Age
Sex/gender
Ethnicity where reported
Baseline disease severity
Diagnostic criteria
Comorbidities
Previous treatment
Socioeconomic or equity characteristics
Intervention
Name and components
Dose/intensity
Frequency
Duration
Mode of delivery
Provider
Co-interventions
Adherence
Fidelity
Modifications
Comparator
Record the same level of detail as for the intervention. “Usual care” should not be left undefined.
Outcomes

For every result:

- Outcome name
- Definition
- Measurement instrument
- Time point
- Analysis population
- Units
- Direction of benefit
- Number analyzed in each group
- Mean and SD
- Number of events and total
- Hazard ratio and confidence interval
- Adjusted or unadjusted estimate
- Variables used for adjustment
- Missing data
- Source page/table/figure
- Extractor notes
- Risk-of-bias information

Extract verbatim support for later judgments:

- Random-sequence method
- Allocation concealment
- Blinding
- Missing outcome data
- Deviations from intervention
- Prespecified analysis
- Outcome-reporting discrepancies

28. Pilot the extraction form
-----------------------------

Test on several varied studies.

Check whether:

- Two reviewers interpret fields similarly
- Units are clear
- Time points are unambiguous
- Missing data can be distinguished from zero
- Multiple arms can be represented
- Multiple reports can be linked
- Quotes and page numbers are captured
- The form contains unnecessary fields
- Important fields are missing
- Freeze a version after piloting. Later changes should be versioned and documented.

29. Extract independently and verify
------------------------------------

Critical data, especially outcome data, should be extracted independently by at least two people. Cochrane treats duplicate outcome-data extraction as mandatory.
Resolve discrepancies by checking the source, not by averaging the two values.

Maintain:

- Raw extraction from reviewer A
- Raw extraction from reviewer B
- Reconciled consensus value
- Explanation of important corrections

Contact authors when necessary for:

- Missing numerical results
- Unclear denominators
- Unclear study eligibility
- Unreported standard deviations
- Overlapping study samples
- Inconsistent reports
- Record the date, request and response.

Phase 12: Assess risk of bias
=============================

30. Choose the tool based on study design
-----------------------------------------

Examples:

| Study design | Common tool |
| --- | --- |
| Randomized intervention trial | Cochrane RoB 2 |
| Non-randomized intervention study | ROBINS-I |
| Diagnostic-accuracy study | QUADAS-2 or its current successor where applicable |
| Prediction-model study | PROBAST |
| Systematic review included in an overview | ROBIS |
| Non-randomized exposure study | ROBINS-E |
| Animal intervention study | SYRCLE RoB tool |

Do not select a tool simply because it is easy or popular.
RoB 2 examines bias in a particular result, including randomization, deviations from intended interventions, missing data, outcome measurement and selection of the reported result.
ROBINS-I addresses confounding, selection, intervention classification, deviations, missing data, outcome measurement and selective reporting in non-randomized intervention studies.

31. Define the estimand
-----------------------

Before applying RoB 2, clarify what effect is being assessed:

- Effect of assignment to intervention, similar to intention-to-treat
- Effect of adhering to intervention
- Risk-of-bias judgments may differ depending on the estimand.

32. Assess independently
------------------------

For each relevant outcome or result:

- Answer signaling questions.
- Record supporting quotations and page numbers.
- Apply the tool’s algorithm.
- Use reviewer judgment where required.
- Resolve differences by consensus or adjudication.
- Preserve original assessments.

Do not:

- Replace domain judgments with a home-made numerical score.
- Call reporting quality “risk of bias.”
- Assume randomization automatically means low risk.
- Rate the whole paper once when bias differs by outcome.
- Let the study’s result direction influence the assessment.

Phase 13: Prepare the synthesis
===============================

33. Clean and verify the dataset
--------------------------------

Before analysis:

- Confirm every included study has one study ID.
- Check for duplicate participants.
- Check sample sizes against the publication.
- Check units.
- Confirm outcome direction.
- Distinguish zero from missing.
- Confirm decimal places.
- Verify all calculated values.
- Confirm time-point classifications.
- Check that totals are internally consistent.
- Recalculate a sample of derived values independently.
- Lock a dated analysis dataset.
- Create a change log rather than silently editing the locked file.

34. Define synthesis groups
---------------------------

Studies should be grouped according to prespecified logic:

- Population
- Intervention type
- Comparator
- Outcome
- Time point
- Study design
- Effect measure
- Clinical setting
- Eligibility for the review does not automatically imply eligibility for every meta-analysis.

Example synthesis:

Adults with primary hypertension; telemonitoring with professional feedback versus usual care; mean systolic BP at approximately six months; randomized trials only.

35. Decide whether meta-analysis is appropriate
-----------------------------------------------

Consider:

- Are the populations sufficiently comparable?
- Are the interventions conceptually similar?
- Are the comparators compatible?
- Are outcomes measuring the same construct?
- Are time points reasonably aligned?
- Are study designs compatible?
- Would a pooled average have a meaningful interpretation?
- Do not decide solely from the value of \(I^2\). Clinical and methodological compatibility must be considered before statistical heterogeneity is calculated.
- If pooling is inappropriate, use a structured synthesis without meta-analysis and follow the SWiM guideline. Avoid informal vote counting based on the number of “statistically significant” studies.

Phase 14: Perform the meta-analysis
===================================

36. Select the effect measure
-----------------------------

| Outcome type | Common effect measure |
| --- | --- |
| Binary | Risk ratio, odds ratio or risk difference |
| Continuous, same instrument | Mean difference |
| Continuous, different instruments measuring same construct | Standardized mean difference |
| Time-to-event | Hazard ratio |
| Event rate/person-time | Incidence-rate ratio |
| Correlation | Transformed correlation coefficient |
| Prevalence | Proportion using an appropriate transformation/model |

Prespecify:

- Preferred effect measure
- Direction of benefit
- Method for conversion
- Handling of adjusted estimates
- Handling of zero events
- Do not mix odds ratios and risk ratios as though they were the same.

37. Handle special designs correctly
------------------------------------

Multi-arm trials

Avoid counting the shared comparator twice. Options include:

- Combine similar intervention arms.
- Split the comparator appropriately.
- Use a multivariate method.
- Cluster-randomized trials
- Use a cluster-adjusted estimate or adjust for the design effect using the intracluster correlation coefficient.
- Cross-over trials
- Use paired analysis where possible. Do not analyze them automatically as parallel trials.
- Repeated measurements
- Use the prespecified time-point hierarchy. Do not select the time point with the largest effect.
- Multiple outcome scales
- Use a predefined hierarchy or standardized effect measure.
- Change scores
- Account for the correlation between baseline and follow-up when deriving variances. Conduct sensitivity analyses if an assumed correlation is required.

38. Choose the model
--------------------

A fixed-effect model assumes one common underlying effect. A random-effects model assumes effects vary across studies and estimates an average of a distribution of effects.

Prespecify:

- Model
- Between-study variance estimator
- Confidence-interval method
- Software and package versions
- Handling of small numbers of studies
- Random-effects analysis is not an automatic solution to heterogeneity. It changes the interpretation and may give relatively more weight to smaller studies.

39. Assess heterogeneity
------------------------

Report:

- Clinical heterogeneity
- Methodological heterogeneity
- Statistical heterogeneity
- \(I^2\)
- \(\tau^2\)
- Cochran’s \(Q\) where appropriate
- Prediction interval when meaningful and sufficiently supported
- Cochrane emphasizes that heterogeneity must be interpreted through the magnitude and direction of effects, not through rigid \(I^2\) thresholds alone.

Investigate unexpected heterogeneity by checking:

- Data-entry errors
- Outcome definitions
- Follow-up periods
- Intervention intensity
- Population severity
- Study design
- Risk of bias
- Effect-measure direction
- Unit conversions

40. Conduct prespecified subgroup analyses
------------------------------------------

Possible subgroups might include:

- Age
- Baseline severity
- Intervention intensity
- Setting
- Risk of bias
- Follow-up duration
- Compare subgroups using a formal interaction test. Do not claim subgroup differences because one subgroup is statistically significant and another is not.

Treat subgroup findings cautiously when:

- They were not prespecified.
- There are few studies.
- Many subgroup analyses were conducted.
- The proposed explanation lacks biological plausibility.
- Differences are based on study-level rather than participant-level characteristics.

41. Conduct sensitivity analyses
--------------------------------

Examples:

- Excluding studies at high risk of bias
- Fixed-effect versus random-effects model
- Alternative \(\tau^2\) estimators
- Excluding imputed data
- Adjusted versus unadjusted estimates
- Change scores versus final values
- Excluding unpublished studies
- Excluding cluster trials requiring assumed ICC values
- Alternative definitions of intervention eligibility
- Leave-one-out analysis for influential studies
- Sensitivity analyses test robustness; they should not be used to search for the most attractive result.

42. Assess missing evidence and reporting bias
----------------------------------------------

Methods include:

- Comparing protocols, registries and publications
- Looking for missing outcomes
- Searching trial registries
- Contacting authors
- Examining funnel plots
- Testing funnel-plot asymmetry when appropriate
- Considering small-study effects
- As a rule of thumb, formal funnel-plot asymmetry tests should generally be used only when a meta-analysis contains at least ten studies, and even then they have limitations. Funnel asymmetry is not proof of publication bias.

Phase 15: Assess certainty of evidence
======================================

43. Apply GRADE by outcome
--------------------------

GRADE evaluates confidence in a body of evidence for each important outcome—not the overall quality of a paper and not one score for the whole review.

For randomized evidence, consider downgrading for:

- Risk of bias
- Inconsistency
- Indirectness
- Imprecision
- Publication or dissemination bias

Possible levels are:

- High certainty
- Moderate certainty
- Low certainty
- Very low certainty

Prepare a Summary of Findings table containing:

- Outcome
- Time point
- Number of studies
- Number of participants
- Relative effect
- Absolute effect
- Certainty
- Reasons for downgrading
- Plain-language interpretation
- Keep the table focused on the most decision-relevant outcomes. The official GRADE Book is replacing the older handbook progressively during 2026.
- A systematic review ordinarily summarizes evidence; it should not casually issue clinical recommendations. Recommendations require additional judgments concerning benefits, harms, values, feasibility, equity and resources.

Phase 16: Write the manuscript
==============================

44. Write according to PRISMA 2020
----------------------------------

PRISMA 2020 contains a 27-item checklist, an abstract checklist and flow-diagram templates. Use the current official checklist when reporting. The notes below are reminders for this workflow.
Title
Identify the report as a systematic review. Add “meta-analysis” only if applicable.
Abstract

Use a structured abstract:

- Background
- Objective
- Eligibility criteria
- Information sources and final search date
- Risk-of-bias method
- Synthesis method
- Number of included studies/participants
- Main numerical results with confidence intervals
- Certainty
- Limitations
- Conclusions
- Registration number
- Funding
- Do not present only p-values.
- Introduction
- Rationale

Explain:

- Clinical or scientific problem
- Current uncertainty
- Existing reviews
- Why another review is needed
- How this review differs
- Objective
- State the complete research question, preferably in PICO form.
- Methods
- Report what was actually done, not merely what the protocol planned.

Include:

- Protocol and registration
- Amendments
- Eligibility criteria
- Information sources
- Complete final search date
- Search strategy
- Deduplication
- Screening process
- Number of reviewers
- Automation tools
- Full-text exclusion process
- Data extraction
- Outcome definitions
- Risk-of-bias method
- Effect measures
- Synthesis eligibility
- Statistical model
- Heterogeneity methods
- Subgroups
- Sensitivity analyses
- Reporting-bias assessment
- Certainty assessment
- Software and versions
- Results

Present in this order:

- Search and selection results
- PRISMA flow diagram
- Included-study characteristics
- Risk-of-bias results
- Results of individual studies
- Results of each synthesis
- Heterogeneity
- Subgroup and sensitivity analyses
- Reporting-bias assessment
- Certainty of evidence
- Report effect sizes with confidence intervals and participant counts.

Distinguish:

- “No evidence of an effect”
- “Evidence of no important effect”
- These are not equivalent.
- Discussion

A strong discussion includes:

- Principal findings
- Summarize the direction, magnitude, precision and certainty of the main results.
- Comparison with previous evidence

Explain agreement or disagreement with:

- Earlier reviews
- Guidelines
- Large individual studies
- Mechanistic expectations
- Strengths

Examples:

- Prospective protocol
- Librarian-designed search
- No language restriction
- Duplicate screening and extraction
- Appropriate bias tool
- Prespecified analysis
- Transparent data and code
- Limitations of included evidence

Examples:

- Small trials
- Short follow-up
- Poor blinding
- Inconsistent outcome definitions
- Missing adverse-event reporting
- Selective reporting
- Indirect populations
- Limitations of the review process

Examples:

- Inability to retrieve reports
- Translation limitations
- Necessary protocol deviations
- Missing data
- Few studies
- Inability to assess publication bias
- Reliance on study-level subgroups
- Implications

Separate:

- Implications for practice
- Implications for policy
- Implications for research
- Keep conclusions proportional to certainty.

Bad:

Telemonitoring should be implemented for all patients.

Better:

Telemonitoring may modestly reduce systolic blood pressure, but uncertainty about long-term clinical outcomes and implementation burden limits strong practice conclusions.

Other declarations

Include:

- Registration
- Protocol availability
- Data availability
- Code availability
- Funding
- Sponsor’s role
- Conflicts of interest
- Author contributions
- Acknowledgments
- AI-use disclosure
- Humans remain responsible for AI-assisted content, citations, originality and analysis. Follow current ICMJE recommendations when disclosing the use of AI.

Phase 17: Prepare tables, figures and supplements
=================================================

45. Minimum recommended outputs
-------------------------------

Main manuscript
PRISMA flow diagram
Characteristics-of-included-studies table
Risk-of-bias figure
Main forest plots
Summary of Findings table
Supplementary materials
Full protocol
Protocol amendments
Complete search strategies for every source
Search log
List of full-text exclusions with reasons
Data-extraction form
Detailed study-characteristics table
Complete risk-of-bias judgments and supporting quotations
Additional forest plots
Sensitivity analyses
Funnel plots where appropriate
Statistical code
De-identified extraction dataset
Completed PRISMA checklist
AI/automation description

Every manuscript claim about an included study should be traceable to:

Manuscript sentence → synthesis result → extraction field → study report → page/table/figure.

Phase 18: Quality control before submission
===========================================

46. Conduct an independent audit
--------------------------------

Have someone who did not produce the main analysis check:

- Search
- All planned databases searched
- Exact strategies preserved
- Dates correct
- Counts match exports
- Update search completed
- Screening
- Two-reviewer decisions preserved
- Full-text reasons specific
- Study and report counts distinguished
- PRISMA counts reconcile mathematically
- Extraction
- Sample sizes match publications
- Events and totals not reversed
- SD and SE not confused
- Units correct
- Intervention direction correct
- Study reports correctly linked
- Missing and zero values distinguished
- Analysis
- Effect directions correct
- Shared comparators not double-counted
- Cluster designs adjusted
- Model matches protocol
- Sensitivity analyses reproducible
- Forest-plot values match tables
- Code reproduces the manuscript numbers
- Writing
- Abstract matches full text
- Methods describe actual procedures
- Conclusions match effect magnitude and certainty
- No invented citations
- No selective emphasis on favorable outcomes
- All protocol deviations disclosed
- PRISMA checklist complete

47. Update the search
---------------------

Rerun the searches close to submission. Cochrane requires searches to be rerun within 12 months of publication and preferably within six months. Newly identified records must be screened and incorporated or transparently reported.

Phase 19: Journal submission and peer review
============================================

48. Select the journal realistically
------------------------------------

Check:

- Scope
- Whether systematic reviews are accepted
- Whether protocol registration is expected
- Reporting guideline
- Word and figure limits
- Open-access charges
- Data-sharing requirements
- AI policy
- Whether a protocol publication creates any issue
- Whether the journal requires PRISMA and supplemental searches
- Avoid predatory journals.

49. Prepare the submission package
----------------------------------

Usually include:

- Manuscript
- Cover letter
- PRISMA checklist with page numbers
- PRISMA flow diagram
- Supplementary files
- Registration number
- Conflict-of-interest forms
- Author contribution statement
- Data/code repository link
- AI-use declaration
- Suggested reviewers if requested

The cover letter should state:

- Why the review is needed
- Its main contribution
- Whether it is registered
- Whether the manuscript is submitted elsewhere
- Whether related manuscripts exist
- How AI was used, if required

50. Respond to reviewers
------------------------

Create a point-by-point response:

Reviewer 1, Comment 3:

[Quote the comment]

Response:

Thank you. We have now...

Change in manuscript:

Page X, paragraph Y:

“Revised text...”

Do not quietly alter methods to satisfy a reviewer. If a requested analysis is post hoc:

- Label it exploratory.
- Preserve the original analysis.
- Explain why it was added.
- Avoid replacing the prespecified primary result.

Phase 20: Archive, publish and update
=====================================

51. Create a reproducibility archive
------------------------------------

Preserve:

- Protocol versions
- Registration record
- Raw search exports
- Search strategies
- Deduplication log
- Screening decisions
- Full-text exclusion reasons
- Extraction forms
- Consensus dataset
- Risk-of-bias files
- Statistical code
- Generated tables and figures
- Submitted manuscript
- Reviewer responses
- Accepted manuscript
- Final citation
- Use stable repositories where possible and avoid sharing copyrighted full-text PDFs publicly.

52. Plan updates
----------------

Define triggers such as:

- A major new trial
- A prespecified date
- A new safety signal
- A change in clinical practice
- A conclusion likely to change
- A guideline-development request

For a living review:

- Schedule recurring searches.
- Deduplicate against the existing library.
- Screen new records.
- Extract and assess new studies.
- Re-run analyses.
- Version all outputs.
- Publish update notices.

Common mistakes that invalidate or weaken reviews
=================================================

Starting screening before finalizing the protocol.
Choosing a topic without checking existing reviews.
Using PRISMA as though it were a conduct manual.
Searching only PubMed.
Using Google Scholar as the sole search source.
Creating an overly narrow search containing every PICO element.
Restricting language or date without justification.
Using only one reviewer for final inclusion decisions.
Failing to record full-text exclusion reasons.
Treating multiple reports as multiple studies.
Extracting only significant outcomes.
Selecting the most favorable time point.
Confusing SD with SE.
Pooling clinically incompatible studies.
Choosing fixed or random effects after seeing the result.
Treating \(I^2\) as the sole decision rule.
Performing many post-hoc subgroups.
Claiming subgroup differences without an interaction test.
Using funnel plots with too few studies.
Equating funnel asymmetry with publication bias.
Treating risk of bias as a simple numerical quality score.
Confusing risk of bias with certainty of evidence.
Concluding “no effect” from an imprecise nonsignificant result.
Changing outcomes after seeing results without disclosure.
Writing conclusions stronger than the evidence.
Allowing AI-generated prose to introduce unsupported citations.
Failing to update the search before submission.
Keeping no reproducible dataset or statistical code.

Where AI fits in this workflow
==============================

AI can safely assist with:

- Generating candidate synonyms
- Translating search syntax for librarian review
- Deduplication suggestions
- Screening prioritization
- Locating relevant text in full reports
- Drafting extraction entries with source quotations
- Detecting inconsistent numbers
- Generating manuscript scaffolding
- Checking PRISMA completeness
- Formatting references and tables
- Monitoring for new studies

Human approval remains essential for:

- Research question and protocol
- Search strategy
- Final study eligibility
- Critical outcome extraction
- Risk of bias
- Statistical decisions
- GRADE judgments
- Interpretation and conclusions

The best automation target is therefore not “AI writes a systematic review.” It is:

AI maintains a complete, auditable chain of evidence while humans approve the relatively small number of decisions that could change the scientific conclusion.
