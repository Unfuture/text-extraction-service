# Text Extraction Service - Decision Matrix

## Quick Comparison

```
+------------------+-------------------+-------------------+-------------------+
|    Criteria      | Option 1:         | Option 2:         | Option 3:         |
|                  | Microservice      | Serverless        | Library + Svc     |
+------------------+-------------------+-------------------+-------------------+
| Setup Time       | 3.5 weeks (144h)  | 3 weeks (112h)    | 3.25 weeks (136h) |
| Monthly Cost     | 3,850-4,130 EUR   | 3,730 EUR         | 3,600 EUR*        |
| Operational Load | High              | Low               | Low-Medium        |
| Scalability      | Manual (K8s)      | Automatic         | Per-consumer      |
| GDPR Compliance  | Excellent         | Good (EU region)  | Excellent         |
| Vendor Lock-in   | None              | High (GCP)        | None              |
| Flexibility      | Medium            | Low               | High              |
+------------------+-------------------+-------------------+-------------------+
* Library-only cost: 0 EUR infrastructure + per-consumer Langdock API
```

## Detailed Scoring (1-5, higher is better)

| Criterion | Weight | Option 1 | Option 2 | Option 3 |
|-----------|--------|----------|----------|----------|
| **Development** |  |  |  |  |
| Time to MVP | 15% | 3 | 4 | 4 |
| Code Reusability | 10% | 3 | 2 | 5 |
| Testing Ease | 10% | 4 | 3 | 5 |
| **Operations** |  |  |  |  |
| Maintenance Effort | 15% | 2 | 4 | 4 |
| Monitoring/Debugging | 10% | 5 | 3 | 4 |
| Scaling | 10% | 4 | 5 | 4 |
| **Business** |  |  |  |  |
| Total Cost of Ownership | 15% | 3 | 4 | 5 |
| GDPR Compliance | 10% | 5 | 3 | 5 |
| Vendor Independence | 5% | 5 | 2 | 5 |
| **Weighted Score** | 100% | **3.40** | **3.45** | **4.50** |

## Scenario-Based Recommendations

### Scenario A: Single Consumer (list-eingangsrechnungen only)
**Recommendation: Option 3 (Library)**

- Direct integration, no network overhead
- Lowest complexity
- Easy to extend later

### Scenario B: Multiple Python Consumers
**Recommendation: Option 3 (Library + Service)**

- Library for Python apps
- Service wrapper for batch APIs
- Centralized configuration

### Scenario C: Multi-Language Consumers
**Recommendation: Option 1 (Microservice)**

- REST API for any language
- Full job tracking
- Higher complexity justified

### Scenario D: High-Volume Processing (>100K docs/month)
**Recommendation: Option 2 (Serverless)**

- Auto-scaling
- Pay-per-use efficiency
- Accept vendor lock-in tradeoff

## Risk Assessment

### Option 1: Microservice
```
Risk: Infrastructure Management
Severity: Medium
Mitigation: Use managed services (Cloud SQL, Memorystore)
Residual: Still requires K8s expertise

Risk: Over-engineering
Severity: Medium
Mitigation: Start simple, add complexity as needed
Residual: Technical debt if not careful
```

### Option 2: Serverless
```
Risk: Cold Start Latency
Severity: High
Mitigation: Keep functions warm, use Gen 2
Residual: 2-5s first-request latency

Risk: Vendor Lock-in
Severity: High
Mitigation: Abstraction layer for cloud services
Residual: Migration effort if switching clouds

Risk: GDPR Data Residency
Severity: Medium
Mitigation: EU region deployment
Residual: Still cloud-hosted data
```

### Option 3: Library + Service
```
Risk: Dependency Management
Severity: Low
Mitigation: Semantic versioning, changelog
Residual: Version conflicts possible

Risk: No Centralized Monitoring (library-only)
Severity: Low
Mitigation: Structured logging, consumer-side monitoring
Residual: Distributed observability
```

## Migration Effort from Current Implementation

| Component | Lines of Code | Option 1 | Option 2 | Option 3 |
|-----------|---------------|----------|----------|----------|
| pdf_type_detector.py | 354 | Rewrite | Rewrite | Extract |
| two_pass_ocr_processor.py | 637 | Rewrite | Adapt | Extract |
| langdock_inline_client.py | 354 | Rewrite | Rewrite | Extract |
| assistant_config.py | 213 | Rewrite | Rewrite | Extract |
| json_repair.py | 271 | Rewrite | Rewrite | Extract |
| **Total Effort** | **~1,800** | **High** | **Medium** | **Low** |

## Final Recommendation

```
+-----------------------------------------------------------------------+
|                                                                        |
|   RECOMMENDED: Option 3 - Library Package + Service                   |
|                                                                        |
|   Primary Reasons:                                                     |
|   1. Lowest migration risk (extract existing code)                    |
|   2. Maximum flexibility (library or service as needed)               |
|   3. Best GDPR compliance (data stays local with library)             |
|   4. Lowest total cost of ownership                                   |
|   5. Aligns with current Python/FastAPI tech stack                    |
|                                                                        |
|   Implementation Priority:                                             |
|   Week 1-2: Extract core library, publish to private PyPI             |
|   Week 3:   Migrate list-eingangsrechnungen to use library            |
|   Week 4+:  Add service wrapper if/when additional consumers emerge    |
|                                                                        |
+-----------------------------------------------------------------------+
```

## Appendix: Technology Comparison

### PDF Processing Libraries

| Library | License | Speed | Features | Recommendation |
|---------|---------|-------|----------|----------------|
| PyMuPDF | AGPL/Commercial | Fast | Full-featured | Current choice |
| pypdf | BSD | Medium | Pure Python | Simpler use cases |
| pdfplumber | MIT | Slow | Table extraction | Specific needs |
| pdf2image | MIT | Medium | Image conversion | OCR pipeline |

### OCR Backends

| Backend | Cost | Accuracy | Speed | Use Case |
|---------|------|----------|-------|----------|
| Claude Sonnet 4.5 | High | Excellent | Medium | Primary (scanned) |
| GPT-4o | High | Very Good | Fast | Analysis |
| Tesseract 5.3 | Free | Good | Fast | Fallback |
| Cloud Vision | Medium | Very Good | Fast | Alternative |

### Database Options (if needed)

| Database | Use Case | Recommendation |
|----------|----------|----------------|
| PostgreSQL | Full ACID, complex queries | Service option |
| SQLite | Simple local storage | Library testing |
| Redis | Caching, job queue | Service option |
| Firestore | Serverless | Option 2 only |

---

*Decision Matrix Version: 1.0*
*Last Updated: 2026-01-07*
