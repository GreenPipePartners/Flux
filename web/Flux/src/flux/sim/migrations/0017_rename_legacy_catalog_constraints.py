from django.db import migrations, models


FORWARD_SQL = """
ALTER TABLE "sim"."provider_node" RENAME CONSTRAINT "unique_base_tag_node_path" TO "unique_sim_provider_node_path";
ALTER INDEX "sim"."base_tagnod_provide_575f83_idx" RENAME TO "sim_provider_node_parent_idx";
ALTER INDEX "sim"."base_tagnod_provide_db4760_idx" RENAME TO "sim_provider_node_sort_idx";
ALTER INDEX "sim"."base_tagnod_provide_ac3d40_idx" RENAME TO "sim_provider_node_depth_idx";
ALTER INDEX "sim"."base_tagnod_provide_4968b0_idx" RENAME TO "sim_provider_node_type_idx";
ALTER INDEX "sim"."base_tagnod_provide_216a5b_idx" RENAME TO "sim_provider_node_source_idx";
ALTER INDEX "sim"."base_tagnod_provide_970d48_idx" RENAME TO "sim_provider_node_data_idx";

ALTER TABLE "sim"."provider_selection" RENAME CONSTRAINT "unique_base_tag_selection" TO "unique_sim_provider_selection_path";

ALTER TABLE "sim"."device" RENAME CONSTRAINT "device_driver_id_a5afbcbe_fk_base_simdriver_id" TO "sim_device_driver_id_fk";
ALTER TABLE "sim"."device" RENAME CONSTRAINT "device_endpoint_id_008337e7_fk_base_fieldendpoint_id" TO "sim_device_endpoint_id_fk";
ALTER TABLE "sim"."device" RENAME CONSTRAINT "device_sim_server_id_10dd01af_fk_base_simserver_id" TO "sim_device_server_id_fk";
ALTER TABLE "sim"."device" RENAME CONSTRAINT "device_source_provider_id_ab7e9335_fk_base_tagprovider_id" TO "sim_device_provider_id_fk";
ALTER TABLE "sim"."provider" RENAME CONSTRAINT "base_tagprovider_sim_server_id_362de107_fk_base_simserver_id" TO "sim_provider_server_id_fk";
ALTER TABLE "sim"."provider_node" RENAME CONSTRAINT "base_tagnode_parent_id_fb971dad_fk_base_tagnode_id" TO "sim_provider_node_parent_id_fk";
ALTER TABLE "sim"."provider_node" RENAME CONSTRAINT "base_tagnode_provider_id_ddb54cf8_fk_base_tagprovider_id" TO "sim_provider_node_provider_id_fk";
ALTER TABLE "sim"."provider_selection" RENAME CONSTRAINT "base_tagselection_provider_id_fdec58f7_fk_base_tagprovider_id" TO "sim_provider_selection_provider_id_fk";
ALTER TABLE "sim"."tag" RENAME CONSTRAINT "tag_source_tag_node_id_4651bf44_fk_base_tagnode_id" TO "sim_tag_provider_node_id_fk";

ALTER INDEX "sim"."base_tagprovider_sim_server_id_362de107" RENAME TO "sim_provider_server_id_idx";
ALTER INDEX "sim"."base_tagnode_parent_id_fb971dad" RENAME TO "sim_provider_node_parent_id_idx";
ALTER INDEX "sim"."base_tagnode_provider_id_ddb54cf8" RENAME TO "sim_provider_node_provider_id_idx";
ALTER INDEX "sim"."base_tagselection_provider_id_fdec58f7" RENAME TO "sim_provider_selection_provider_id_idx";
"""


REVERSE_SQL = """
ALTER INDEX "sim"."sim_provider_selection_provider_id_idx" RENAME TO "base_tagselection_provider_id_fdec58f7";
ALTER INDEX "sim"."sim_provider_node_provider_id_idx" RENAME TO "base_tagnode_provider_id_ddb54cf8";
ALTER INDEX "sim"."sim_provider_node_parent_id_idx" RENAME TO "base_tagnode_parent_id_fb971dad";
ALTER INDEX "sim"."sim_provider_server_id_idx" RENAME TO "base_tagprovider_sim_server_id_362de107";

ALTER TABLE "sim"."tag" RENAME CONSTRAINT "sim_tag_provider_node_id_fk" TO "tag_source_tag_node_id_4651bf44_fk_base_tagnode_id";
ALTER TABLE "sim"."provider_selection" RENAME CONSTRAINT "sim_provider_selection_provider_id_fk" TO "base_tagselection_provider_id_fdec58f7_fk_base_tagprovider_id";
ALTER TABLE "sim"."provider_node" RENAME CONSTRAINT "sim_provider_node_provider_id_fk" TO "base_tagnode_provider_id_ddb54cf8_fk_base_tagprovider_id";
ALTER TABLE "sim"."provider_node" RENAME CONSTRAINT "sim_provider_node_parent_id_fk" TO "base_tagnode_parent_id_fb971dad_fk_base_tagnode_id";
ALTER TABLE "sim"."provider" RENAME CONSTRAINT "sim_provider_server_id_fk" TO "base_tagprovider_sim_server_id_362de107_fk_base_simserver_id";
ALTER TABLE "sim"."device" RENAME CONSTRAINT "sim_device_provider_id_fk" TO "device_source_provider_id_ab7e9335_fk_base_tagprovider_id";
ALTER TABLE "sim"."device" RENAME CONSTRAINT "sim_device_server_id_fk" TO "device_sim_server_id_10dd01af_fk_base_simserver_id";
ALTER TABLE "sim"."device" RENAME CONSTRAINT "sim_device_endpoint_id_fk" TO "device_endpoint_id_008337e7_fk_base_fieldendpoint_id";
ALTER TABLE "sim"."device" RENAME CONSTRAINT "sim_device_driver_id_fk" TO "device_driver_id_a5afbcbe_fk_base_simdriver_id";

ALTER TABLE "sim"."provider_selection" RENAME CONSTRAINT "unique_sim_provider_selection_path" TO "unique_base_tag_selection";

ALTER INDEX "sim"."sim_provider_node_data_idx" RENAME TO "base_tagnod_provide_970d48_idx";
ALTER INDEX "sim"."sim_provider_node_source_idx" RENAME TO "base_tagnod_provide_216a5b_idx";
ALTER INDEX "sim"."sim_provider_node_type_idx" RENAME TO "base_tagnod_provide_4968b0_idx";
ALTER INDEX "sim"."sim_provider_node_depth_idx" RENAME TO "base_tagnod_provide_ac3d40_idx";
ALTER INDEX "sim"."sim_provider_node_sort_idx" RENAME TO "base_tagnod_provide_db4760_idx";
ALTER INDEX "sim"."sim_provider_node_parent_idx" RENAME TO "base_tagnod_provide_575f83_idx";
ALTER TABLE "sim"."provider_node" RENAME CONSTRAINT "unique_sim_provider_node_path" TO "unique_base_tag_node_path";
"""


class Migration(migrations.Migration):
    dependencies = [
        ("sim", "0016_drop_legacy_provider_selection"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)],
            state_operations=[
                migrations.RemoveConstraint(model_name="providernode", name="unique_base_tag_node_path"),
                migrations.AddConstraint(
                    model_name="providernode",
                    constraint=models.UniqueConstraint(fields=("provider", "path"), name="unique_sim_provider_node_path"),
                ),
                migrations.RemoveConstraint(model_name="providerselection", name="unique_base_tag_selection"),
                migrations.AddConstraint(
                    model_name="providerselection",
                    constraint=models.UniqueConstraint(fields=("provider", "purpose", "path"), name="unique_sim_provider_selection_path"),
                ),
                migrations.RenameIndex(model_name="providernode", old_name="base_tagnod_provide_575f83_idx", new_name="sim_provider_node_parent_idx"),
                migrations.RenameIndex(model_name="providernode", old_name="base_tagnod_provide_db4760_idx", new_name="sim_provider_node_sort_idx"),
                migrations.RenameIndex(model_name="providernode", old_name="base_tagnod_provide_ac3d40_idx", new_name="sim_provider_node_depth_idx"),
                migrations.RenameIndex(model_name="providernode", old_name="base_tagnod_provide_4968b0_idx", new_name="sim_provider_node_type_idx"),
                migrations.RenameIndex(model_name="providernode", old_name="base_tagnod_provide_216a5b_idx", new_name="sim_provider_node_source_idx"),
                migrations.RenameIndex(model_name="providernode", old_name="base_tagnod_provide_970d48_idx", new_name="sim_provider_node_data_idx"),
            ],
        ),
    ]
