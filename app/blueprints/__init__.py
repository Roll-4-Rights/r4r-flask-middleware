from app.blueprints.admin import bp as admin_bp
from app.blueprints.auction import bp as auction_bp
from app.blueprints.auth import bp as auth_bp
from app.blueprints.bidder import bp as bidder_bp
from app.blueprints.calendar import bp as calendar_bp
from app.blueprints.campaign import bp as campaign_bp
from app.blueprints.content import bp as content_bp
from app.blueprints.donations import bp as donations_bp
from app.blueprints.forum import bp as forum_bp
from app.blueprints.health import bp as health_bp
from app.blueprints.media import bp as media_bp
from app.blueprints.messages import bp as messages_bp
from app.blueprints.profile import bp as profile_bp
from app.blueprints.root import bp as root_bp
from app.blueprints.tables import bp as tables_bp
from app.blueprints.winner_claim import bp as winner_claim_bp


def register_blueprints(app):
    for blueprint in (
        health_bp,
        auth_bp,
        donations_bp,
        messages_bp,
        calendar_bp,
        auction_bp,
        bidder_bp,
        winner_claim_bp,
        campaign_bp,
        content_bp,
        tables_bp,
        media_bp,
        profile_bp,
        forum_bp,
        admin_bp,
        root_bp,
    ):
        app.register_blueprint(blueprint)
