from app import db
from app.models import Project
from app.utils import paginate_query


def test_paginate_query_clamps_invalid_page(ctx):
    db.session.add(Project(name='A'))
    db.session.commit()

    items, total, pages = paginate_query(Project.query.order_by(Project.id), 0, 20)

    assert [item.name for item in items] == ['A']
    assert total == 1
    assert pages == 1


def test_paginate_query_returns_empty_page_for_no_rows(ctx):
    items, total, pages = paginate_query(Project.query, 1, 20)

    assert items == []
    assert total == 0
    assert pages == 0


def test_paginate_request_query_reads_page_from_request(app, ctx):
    from app.utils import paginate_request_query

    db.session.add_all([Project(name=f'P{i}') for i in range(3)])
    db.session.commit()

    with app.test_request_context('/admin/projects?page=2'):
        result = paginate_request_query(Project.query.order_by(Project.id), 'page', 2)

    assert [item.name for item in result.items] == ['P2']
    assert result.page == 2
    assert result.total == 3
    assert result.pages == 2
